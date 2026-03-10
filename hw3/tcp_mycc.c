// tcp_mycc.c
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/types.h>
#include <linux/moduleparam.h>
#include <net/tcp.h>
#include <net/inet_connection_sock.h>

#define MYCC_NAME "mycc"

/*
 * Per-rule toggles for quick A/B testing.
 * Set at module load time, e.g.:
 *   insmod tcp_mycc.ko enable_severe=1 enable_mild=0 enable_lowrate=0
 */
static bool enable_loss_hold = true;
module_param(enable_loss_hold, bool, 0644);
MODULE_PARM_DESC(enable_loss_hold, "Hold growth on Lt>0 (loss seen since last callback)");

static bool enable_severe = true;
module_param(enable_severe, bool, 0644);
MODULE_PARM_DESC(enable_severe, "Enable severe RTT+jitter rule");

static bool enable_mild = false;
module_param(enable_mild, bool, 0644);
MODULE_PARM_DESC(enable_mild, "Enable mild RTT inflation rule");

static bool enable_lowrate = false;
module_param(enable_lowrate, bool, 0644);
MODULE_PARM_DESC(enable_lowrate, "Enable low delivery-rate rule");

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
	u64 g_ref_Bps;          // decaying delivery-rate baseline (bytes/sec)
	u32 prev_total_retrans; // last retrans snapshot (for Lt)
	u32 severe_persist_us;  // persistence timer for severe queue signal
	u32 mild_persist_us;    // persistence timer for mild RTT signal
	u32 lowrate_persist_us; // persistence timer for low delivery signal
	u32 reduce_cooldown_us; // cooldown after a cwnd reduction
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

	ca->g_ref_Bps = 0;
	ca->prev_total_retrans = tp->total_retrans;
	ca->severe_persist_us = 0;
	ca->mild_persist_us = 0;
	ca->lowrate_persist_us = 0;
	ca->reduce_cooldown_us = 0;
}

static void mycc_cong_control(struct sock *sk, const struct rate_sample *rs)
{
	struct tcp_sock *tp = tcp_sk(sk);
	struct mycc *ca = inet_csk_ca(sk);
	u64 gt_Bps = 0, gmin_Bps;
	u32 lt;
	u32 cwnd;
	u32 sample_us;
	u32 severe_persist_target_us;
	u32 soft_persist_target_us;
	u32 cooldown_target_us;
	bool severe_queue;
	bool mild_rtt;
	bool low_rate;

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

	/*
	 * Decaying throughput baseline:
	 * - rise relatively quickly when path improves
	 * - decay slowly when path degrades
	 */
	if (gt_Bps > 0) {
		if (ca->g_ref_Bps == 0) {
			ca->g_ref_Bps = gt_Bps;
		} else if (gt_Bps >= ca->g_ref_Bps) {
			ca->g_ref_Bps = ((ca->g_ref_Bps * 7ULL) + gt_Bps) / 8ULL;
		} else {
			ca->g_ref_Bps = ((ca->g_ref_Bps * 31ULL) + gt_Bps) / 32ULL;
		}
	}
	gmin_Bps = (ca->g_ref_Bps * 65ULL) / 100ULL;

	lt = tp->total_retrans - ca->prev_total_retrans;
	ca->prev_total_retrans = tp->total_retrans;
	cwnd = tp->snd_cwnd;
	sample_us = (rs && rs->interval_us > 0) ? (u32)min_t(long, rs->interval_us, (long)~0U) : 0U;
	if (sample_us == 0)
		sample_us = max(srtt_us / 8U, 1000U);
	severe_persist_target_us = max(srtt_us, 4000U);   // ~= 1 RTT, floor at 4ms
	soft_persist_target_us = max_t(u32, (u32)min_t(u64, (u64)srtt_us * 3ULL, (u64)~0U), 12000U); // ~= 3 RTT, floor at 12ms
	cooldown_target_us = max_t(u32, (u32)min_t(u64, (u64)srtt_us * 2ULL, (u64)~0U), 10000U); // ~= 2 RTT, floor at 10ms

	// Track best rttvar only during low-queue periods.
	if (srtt_us > 0 && srtt_us <= (ca->r0_us * 110) / 100) {
		if (rttvar_us > 0 && rttvar_us < ca->v0_us)
			ca->v0_us = rttvar_us;
	}
	if (ca->v0_us == 0) ca->v0_us = 1;

	if (ca->reduce_cooldown_us > sample_us)
		ca->reduce_cooldown_us -= sample_us;
	else
		ca->reduce_cooldown_us = 0;

	/*
	 * Soft control policy:
	 * - loss (Lt>0) relies on ssthresh logic in TCP core
	 * - delay/rate signals hold growth first
	 * - reduce only after persistence and when not in cooldown
	 */
	if (enable_loss_hold && lt > 0) {
		ca->severe_persist_us = 0;
		ca->mild_persist_us = 0;
		ca->lowrate_persist_us = 0;
		return;
	}

	severe_queue = (srtt_us > (ca->r0_us * 150U) / 100U) &&
		       (rttvar_us > (ca->v0_us * 200U) / 100U);
	mild_rtt = (srtt_us > (ca->r0_us * 140U) / 100U);
	low_rate = (gmin_Bps > 0 && gt_Bps > 0 && gt_Bps < gmin_Bps);

	if (enable_severe && severe_queue) {
		ca->severe_persist_us = min_t(u32, ca->severe_persist_us + sample_us, ~0U);
		ca->mild_persist_us = 0;
		ca->lowrate_persist_us = 0;

		if (ca->reduce_cooldown_us > 0 || ca->severe_persist_us < severe_persist_target_us)
			return; // soft hold first

		cwnd = (cwnd * 85U) / 100U;
		tp->snd_cwnd = mycc_clamp_cwnd(cwnd);
		ca->reduce_cooldown_us = cooldown_target_us;
		ca->severe_persist_us = 0;
		return;
	}
	ca->severe_persist_us = 0;

	if (enable_mild && mild_rtt) {
		ca->mild_persist_us = min_t(u32, ca->mild_persist_us + sample_us, ~0U);
		ca->lowrate_persist_us = 0;

		if (ca->reduce_cooldown_us > 0)
			return;
		if (ca->mild_persist_us >= soft_persist_target_us)
			return; // hold only after sustained mild inflation
	} else {
		ca->mild_persist_us = 0;
	}

	if (enable_lowrate && low_rate) {
		ca->lowrate_persist_us = min_t(u32, ca->lowrate_persist_us + sample_us, ~0U);
		if (ca->reduce_cooldown_us > 0)
			return;
		if (ca->lowrate_persist_us >= soft_persist_target_us)
			return; // hold only after sustained low delivery
	} else {
		ca->lowrate_persist_us = 0;
	}

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
