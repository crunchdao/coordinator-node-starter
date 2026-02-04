import asyncio
import newrelic.agent


async def start_pulse(interval=60):
    """
    An async heartbeat that records a 'Pulse' every minute.
    """
    # Wait a few seconds for New Relic agent to fully connect
    await asyncio.sleep(5)

    app = newrelic.agent.application()

    if app is None:
        # Agent not started with newrelic-admin or initialize()
        return

    while True:
        # We use a standard background_task wrapper here.
        # In async, this records the transaction and immediately returns.
        with newrelic.agent.BackgroundTask(app, name='HeartbeatPulse', group='Python/Heartbeat'):
            pass

        await asyncio.sleep(interval)
