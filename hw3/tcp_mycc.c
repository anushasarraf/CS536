// tcp_mycc.c
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/types.h>
#include <net/tcp.h>
#include <net/inet_connection_sock.h>

#define MYCC_NAME "mycc"

/*
Algorithm:
- ACK path: Reno-style slow start + additive increase.
- Loss path: Reno-style multiplicative decrease through ssthresh callback.
- Keep RTT/rate observations for future tuning, but do not gate cwnd changes on
  a sampling interval.
*/

struct mycc {
	u32 r0_us;              // min srtt seen
	u32 v0_us;              // baseline rttvar (best seen in "good" periods)
	u64 g_peak_Bps;         // peak delivery rate bytes/sec
	u32 prev_total_retrans; // last retrans snapshot (for Lt)
};

static inline u32 mycc_clamp_cwnd(u32 cwnd)
{
	if (cwnd < 2)
		return 2;
	if (cwnd > 1000000)
		return 1000000;
	return cwnd;
}

static void mycc_ack_driven_increase(struct sock *sk, const struct rate_sample *rs)
{
	struct tcp_sock *tp = tcp_sk(sk);
	u32 acked;

	if (!rs || !rs->acked_sacked)
		return;
	if (!tcp_is_cwnd_limited(sk))
		return;

	acked = rs->acked_sacked;
	if (tcp_in_slow_start(tp))
		acked = tcp_slow_start(tp, acked);
	if (acked)
		tcp_cong_avoid_ai(tp, tcp_snd_cwnd(tp), acked);
}

static void mycc_init(struct sock *sk)
{
	struct tcp_sock *tp = tcp_sk(sk);
	struct mycc *ca = inet_csk_ca(sk);

	ca->r0_us = (tp->srtt_us >> 3);
	if (ca->r0_us == 0) ca->r0_us = 1;

	ca->v0_us = tp->rttvar_us;
	if (ca->v0_us == 0) ca->v0_us = 1;

	ca->g_peak_Bps = 0;
	ca->prev_total_retrans = tp->total_retrans;
}

static void mycc_cong_control(struct sock *sk, const struct rate_sample *rs)
{
	struct tcp_sock *tp = tcp_sk(sk);
	struct mycc *ca = inet_csk_ca(sk);
	u64 gt_Bps = 0, gmin_Bps;
	u32 lt;
	u32 cwnd;

	u32 srtt_us = (tp->srtt_us >> 3);
	u32 rttvar_us = tp->rttvar_us;

	// Update baselines
	if (srtt_us > 0 && srtt_us < ca->r0_us)
		ca->r0_us = srtt_us;

	// Estimate goodput from rate_sample in kernels where delivery_rate is absent.
	// delivered is packets over interval_us, so convert to bytes/sec via MSS.
	if (rs && rs->delivered > 0 && rs->interval_us > 0) {
		u64 num = (u64)rs->delivered * (u64)max_t(u32, tp->mss_cache, 1) * 1000000ULL;
		gt_Bps = div64_u64(num, (u64)rs->interval_us);
	}
	if (gt_Bps > ca->g_peak_Bps)
		ca->g_peak_Bps = gt_Bps;
	gmin_Bps = (ca->g_peak_Bps * 80ULL) / 100ULL;

	lt = tp->total_retrans - ca->prev_total_retrans;
	ca->prev_total_retrans = tp->total_retrans;
	cwnd = tp->snd_cwnd;

	// Track best rttvar only during low-queue periods.
	if (srtt_us > 0 && srtt_us <= (ca->r0_us * 110) / 100) {
		if (rttvar_us > 0 && rttvar_us < ca->v0_us)
			ca->v0_us = rttvar_us;
	}
	if (ca->v0_us == 0) ca->v0_us = 1;

	/*
	 * Rule cascade from Eq. (5):
	 * 1) Lt > 0                       => W <- floor(W * 0.5)
	 * 2) Rt > 1.5*R0 && Vt > 2*V0     => W <- floor(W * 0.8)
	 * 3) Rt > 1.25*R0                 => W <- floor(W * 0.9)
	 * 4) Gt < Gmin                    => hold W
	 * 5) otherwise                    => additive increase
	 */
	
	// halving cwnd is already done in mycc_ssthresh
	// if (lt > 0) {
	// 	cwnd = (cwnd * 50U) / 100U;
	// 	tp->snd_cwnd = mycc_clamp_cwnd(cwnd);
	// 	return;
	// }

	// if (srtt_us > (ca->r0_us * 150U) / 100U &&
	//     rttvar_us > (ca->v0_us * 200U) / 100U) {
	// 	cwnd = (cwnd * 80U) / 100U;
	// 	tp->snd_cwnd = mycc_clamp_cwnd(cwnd);
	// 	return;
	// }

	// if (srtt_us > (ca->r0_us * 125U) / 100U) {
	// 	cwnd = (cwnd * 90U) / 100U;
	// 	tp->snd_cwnd = mycc_clamp_cwnd(cwnd);
	// 	return;
	// }

	// if (gmin_Bps > 0 && gt_Bps > 0 && gt_Bps < gmin_Bps)
	// 	return; // hold

	mycc_ack_driven_increase(sk, rs);
}

static u32 mycc_ssthresh(struct sock *sk)
{
	// Reno-style multiplicative decrease on loss events.
	const struct tcp_sock *tp = tcp_sk(sk);
	return max(tp->snd_cwnd >> 1U, 2U);
}

static u32 mycc_undo_cwnd(struct sock *sk)
{
	// Standard undo: return current cwnd
	return tcp_sk(sk)->snd_cwnd;
}

static struct tcp_congestion_ops mycc __read_mostly = {
	.init        = mycc_init,
	.ssthresh    = mycc_ssthresh,
	.cong_control= mycc_cong_control,
	.undo_cwnd   = mycc_undo_cwnd,
	.name        = MYCC_NAME,
	.owner       = THIS_MODULE,
};

static int __init mycc_register(void)
{
	BUILD_BUG_ON(sizeof(struct mycc) > ICSK_CA_PRIV_SIZE);
	return tcp_register_congestion_control(&mycc);
}

static void __exit mycc_unregister(void)
{
	tcp_unregister_congestion_control(&mycc);
}

module_init(mycc_register);
module_exit(mycc_unregister);

MODULE_AUTHOR("CS536");
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Custom TCP congestion control: mycc");
MODULE_VERSION("1.0");
