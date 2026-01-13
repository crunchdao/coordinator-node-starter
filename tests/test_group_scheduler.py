from datetime import datetime, timezone, timedelta

from condorgame_backend.entities.prediction import GroupScheduler, PredictionConfig, PredictionParams
from condorgame_backend.utils.times import DAY, MINUTE, HOUR


def test_group_scheduler_round_robin_basic():
    """
    basic round-robin scheduling and per-asset spacing when no recovery state is involved.
    """
    configs = [
        PredictionConfig(PredictionParams("BTC", 1 * DAY, [5 * MINUTE]), 1 * HOUR, True, 1),
        PredictionConfig(PredictionParams("ETH", 1 * DAY, [5 * MINUTE]), 1 * HOUR, True, 1),
        PredictionConfig(PredictionParams("XAUT", 1 * DAY, [5 * MINUTE]), 1 * HOUR, True, 1),
    ]

    scheduler = GroupScheduler.create_group_schedulers(configs)[0]
    now = datetime.now(timezone.utc)

    params = scheduler.next(now)
    assert params is not None
    assert params.asset == "BTC"
    scheduler.mark_executed("BTC", now)

    # Not due yet => no params returned
    params = scheduler.next(now)
    assert params is None

    assert scheduler.index == 1
    assert scheduler.next_run == now + timedelta(minutes=20)


def test_group_scheduler_skip_when_no_new_prices():
    """
    ensures an asset is skipped when the latest market info is not newer than its last execution time.
    """

    configs = [
        PredictionConfig(PredictionParams("BTC", 1 * DAY, [5 * MINUTE]), 1 * HOUR, True, 1),
        PredictionConfig(PredictionParams("ETH", 1 * DAY, [5 * MINUTE]), 1 * HOUR, True, 1),
        PredictionConfig(PredictionParams("XAUT", 1 * DAY, [5 * MINUTE]), 1 * HOUR, True, 1),
    ]

    scheduler = GroupScheduler.create_group_schedulers(configs)[0]
    now = datetime.now(timezone.utc)

    last_exec = [
        (configs[0].prediction_params, now - timedelta(minutes=60)),  # BTC
        (configs[1].prediction_params, now - timedelta(minutes=40)),  # ETH
        (configs[2].prediction_params, now - timedelta(minutes=20)),  # XAUT
    ]
    scheduler.set_last_executions(last_exec)

    # Force BTC as the current candidate and make the scheduler due
    scheduler.index = scheduler.assets.index("BTC")
    scheduler.next_run = now

    # Outdated info (older than last execution) => should skip BTC
    outdated_info = now - timedelta(minutes=70)
    params = scheduler.next(now, latest_info_dt=outdated_info)
    assert params is None

    # After skip, it should advance to the next asset
    assert scheduler.index == scheduler.assets.index("ETH")


def test_group_scheduler_recover_picks_lru_first():
    """
    after restart, the scheduler should begin with the least-recently executed asset (LRU).
    """
    configs = [
        PredictionConfig(PredictionParams("BTC", 1 * DAY, [5 * MINUTE]), 1 * HOUR, True, 1),
        PredictionConfig(PredictionParams("ETH", 1 * DAY, [5 * MINUTE]), 1 * HOUR, True, 1),
        PredictionConfig(PredictionParams("XAUT", 1 * DAY, [5 * MINUTE]), 1 * HOUR, True, 1),
    ]

    scheduler = GroupScheduler.create_group_schedulers(configs)[0]
    now = datetime.now(timezone.utc)

    last_exec = [
        (configs[0].prediction_params, now - timedelta(minutes=20)),  # BTC
        (configs[1].prediction_params, now - timedelta(minutes=40)),  # ETH
        (configs[2].prediction_params, now - timedelta(minutes=60)),  # XAUT (LRU)
    ]
    scheduler.set_last_executions(last_exec)

    params = scheduler.next(now)
    assert params is not None
    assert params.asset == "XAUT"

    assert scheduler.index == 0  # BTC after XAUT

    # The next_run expectation is based on your current start_from_lru_asset() logic.
    assert scheduler.next_run == now + timedelta(minutes=20)


def test_group_scheduler_recover_all_runs_without_waiting():
    """
    verifies that after recovery with all assets overdue, the scheduler catches up by running all assets sequentially.
    """

    configs = [
        PredictionConfig(PredictionParams("BTC", 1 * DAY, [5 * MINUTE]), 1 * HOUR, True, 1),
        PredictionConfig(PredictionParams("ETH", 1 * DAY, [5 * MINUTE]), 1 * HOUR, True, 1),
        PredictionConfig(PredictionParams("XAUT", 1 * DAY, [5 * MINUTE]), 1 * HOUR, True, 1),
    ]

    scheduler = GroupScheduler.create_group_schedulers(configs)[0]
    now = datetime.now(timezone.utc)

    last_exec = [
        (configs[0].prediction_params, now - timedelta(minutes=120)),  # BTC
        (configs[1].prediction_params, now - timedelta(minutes=140)),  # ETH
        (configs[2].prediction_params, now - timedelta(minutes=160)),  # XAUT (LRU)
    ]
    scheduler.set_last_executions(last_exec)

    params = scheduler.next(now)
    assert params is not None
    assert params.asset == "XAUT"
    scheduler.mark_executed("XAUT", now)

    params = scheduler.next(now)
    assert params is not None
    assert params.asset == "BTC"
    scheduler.mark_executed("BTC", now)

    params = scheduler.next(now)
    assert params is not None
    assert params.asset == "ETH"
    scheduler.mark_executed("ETH", now)

    assert scheduler.index == 2  # XAUT
    assert scheduler.next_run == now + timedelta(minutes=20)


def test_group_scheduler_respects_asset_cooldown():
    """
    ensures the scheduler never schedules the next run before an asset's cooldown (last_exec + prediction_interval).
    """
    configs = [
        PredictionConfig(PredictionParams("BTC", 1 * DAY, [5 * MINUTE]), 1 * HOUR, True, 1),
        PredictionConfig(PredictionParams("ETH", 1 * DAY, [5 * MINUTE]), 1 * HOUR, True, 1),
        PredictionConfig(PredictionParams("XAUT", 1 * DAY, [5 * MINUTE]), 1 * HOUR, True, 1),
    ]

    scheduler = GroupScheduler.create_group_schedulers(configs)[0]
    now = datetime.now(timezone.utc)

    # Pretend ETH was executed very recently -> should impose a minimum wait for ETH
    scheduler.last_exec_ts["ETH"] = (now - timedelta(minutes=5)).timestamp()

    # Force BTC to run now, so that _advance_schedule moves index to ETH
    scheduler.index = scheduler.assets.index("BTC")
    scheduler.next_run = now

    params = scheduler.next(now)
    assert params is not None
    assert params.asset == "BTC"

    # After BTC, the next asset is ETH.
    eth_next_allowed = datetime.fromtimestamp(scheduler.last_exec_ts["ETH"], timezone.utc) + timedelta(seconds=20 * MINUTE)

    assert scheduler.index == scheduler.assets.index("ETH")
    assert scheduler.next_run >= eth_next_allowed