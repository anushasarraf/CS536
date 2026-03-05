// tcp_mycc.c
#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/init.h>
#include <linux/types.h>
#include <linux/jiffies.h>
#include <net/tcp.h>
#include <net/inet_connection_sock.h>

#define MYCC_NAME "mycc"

/*
Algorithm (per sampling interval):
Let Wt = snd_cwnd
Rt = srtt_ms, Vt = rttvar_ms, Lt = delta_total_retrans, Gt = delivery_mbps
R0 = min RTT observed so far
Gmin = 0.8 * peak delivery rate observed so far
V0 = baseline RTT variance (approx, from uncongested periods)

Update rule:
if Lt > 0:           W <- floor(W * 0.5)
else if Rt > 1.5R0 and Vt > 2V0:  W <- floor(W * 0.8)
else if Rt > 1.25R0: W <- floor(W * 0.9)
else if Gt < Gmin:   hold
else:                W <- W + 1
*/

struct mycc {
	u32 r0_us;              // min srtt seen
	u32 v0_us;              // baseline rttvar (best seen in "good" periods)
	u64 g_peak_Bps;         // peak delivery rate bytes/sec
	u32 prev_total_retrans; // last total_retrans snapshot
	unsigned long next_update_jiffies;
	u32 interval_ms;        // sampling interval
};

static inline u32 mycc_clamp_cwnd(u32 cwnd)
{
	// cwnd must be at least 2 in Linux TCP
	if (cwnd < 2) return 2;
	if (cwnd > 1000000) return 1000000;
	return cwnd;
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

	ca->interval_ms = 100; // you can tune this
	ca->next_update_jiffies = jiffies + msecs_to_jiffies(ca->interval_ms);
}

static void mycc_cong_control(struct sock *sk, const struct rate_sample *rs)
{
	struct tcp_sock *tp = tcp_sk(sk);
	struct mycc *ca = inet_csk_ca(sk);

	u32 srtt_us = (tp->srtt_us >> 3);
	u32 rttvar_us = tp->rttvar_us;

	// Update baselines
	if (srtt_us > 0 && srtt_us < ca->r0_us)
		ca->r0_us = srtt_us;

	// Estimate goodput from rate_sample in kernels where delivery_rate is absent.
	// delivered is packets over interval_us, so convert to bytes/sec via MSS.
	{
		u64 gt_Bps = 0;
		if (rs && rs->delivered > 0 && rs->interval_us > 0) {
			u64 num = (u64)rs->delivered * (u64)max_t(u32, tp->mss_cache, 1) * 1000000ULL;
			gt_Bps = div64_u64(num, (u64)rs->interval_us);
		}
		if (gt_Bps > ca->g_peak_Bps)
			ca->g_peak_Bps = gt_Bps;
	}

	// Only update once per interval
	if (time_before(jiffies, ca->next_update_jiffies))
		return;
	ca->next_update_jiffies = jiffies + msecs_to_jiffies(ca->interval_ms);

	// Lt: new retrans since last interval
	{
		u32 tot = tp->total_retrans;
		u32 lt = tot - ca->prev_total_retrans;
		ca->prev_total_retrans = tot;

		u32 W = tp->snd_cwnd;

		// Compute Gmin and current estimated throughput
		u64 gmin_Bps = (ca->g_peak_Bps * 80) / 100;
		u64 gt_Bps = 0;
		if (rs && rs->delivered > 0 && rs->interval_us > 0) {
			u64 num = (u64)rs->delivered * (u64)max_t(u32, tp->mss_cache, 1) * 1000000ULL;
			gt_Bps = div64_u64(num, (u64)rs->interval_us);
		}

		// Update V0 from "good" periods (heuristic):
		// If no loss and RTT not inflated too much, allow v0 to shrink.
		if (lt == 0 && srtt_us <= (ca->r0_us * 110) / 100) {
			if (rttvar_us > 0 && rttvar_us < ca->v0_us)
				ca->v0_us = rttvar_us;
		}
		if (ca->v0_us == 0) ca->v0_us = 1;

		// Apply rule order
		if (lt > 0) {
			W = (W * 50) / 100;
		} else if (srtt_us > (ca->r0_us * 150) / 100 &&
		           rttvar_us > (ca->v0_us * 200) / 100) {
			W = (W * 80) / 100;
		} else if (srtt_us > (ca->r0_us * 125) / 100) {
			W = (W * 90) / 100;
		} else if (gmin_Bps > 0 && gt_Bps > 0 && gt_Bps < gmin_Bps) {
			// hold
			W = W;
		} else {
			W = W + 1;
		}

		tp->snd_cwnd = mycc_clamp_cwnd(W);
	}
}

static u32 mycc_ssthresh(struct sock *sk)
{
	// Keep Linux behavior simple: on loss, tcp will call ssthresh.
	// Our main logic already halves cwnd based on Lt, but this is still used by core TCP.
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
