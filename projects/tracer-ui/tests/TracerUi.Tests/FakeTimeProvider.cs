namespace TracerUi.Tests;

/// <summary>A clock that a test moves by hand, instead of one that makes a test wait on real time.</summary>
public sealed class FakeTimeProvider : TimeProvider
{
    private readonly Lock gate = new();
    private readonly List<ScheduledTimer> scheduled = [];
    private DateTimeOffset now;

    public FakeTimeProvider(DateTimeOffset start) => now = start;

    public override DateTimeOffset GetUtcNow()
    {
        lock (gate)
        {
            return now;
        }
    }

    public override ITimer CreateTimer(TimerCallback callback, object? state, TimeSpan dueTime, TimeSpan period)
    {
        lock (gate)
        {
            var timer = new ScheduledTimer(this, callback, state, now + dueTime, period);
            scheduled.Add(timer);
            return timer;
        }
    }

    /// <summary>
    /// Moves the clock forward by this much, and runs the callback of every timer whose due time
    /// this reaches or passes.
    /// </summary>
    public void Advance(TimeSpan by)
    {
        var due = new List<ScheduledTimer>();
        lock (gate)
        {
            now += by;
            foreach (var timer in scheduled.Where(timer => timer.DueAt <= now).ToArray())
            {
                due.Add(timer);
                if (timer.Period == Timeout.InfiniteTimeSpan)
                {
                    scheduled.Remove(timer);
                }
                else
                {
                    timer.DueAt = now + timer.Period;
                }
            }
        }

        foreach (var timer in due)
        {
            timer.Callback(timer.State);
        }
    }

    private void Forget(ScheduledTimer timer)
    {
        lock (gate)
        {
            scheduled.Remove(timer);
        }
    }

    private void Reschedule(ScheduledTimer timer, TimeSpan dueTime, TimeSpan period)
    {
        lock (gate)
        {
            timer.DueAt = now + dueTime;
            timer.Period = period;
        }
    }

    private sealed class ScheduledTimer(
        FakeTimeProvider clock,
        TimerCallback callback,
        object? state,
        DateTimeOffset dueAt,
        TimeSpan period) : ITimer
    {
        public TimerCallback Callback { get; } = callback;

        public object? State { get; } = state;

        public DateTimeOffset DueAt { get; set; } = dueAt;

        public TimeSpan Period { get; set; } = period;

        public bool Change(TimeSpan dueTime, TimeSpan newPeriod)
        {
            clock.Reschedule(this, dueTime, newPeriod);
            return true;
        }

        public void Dispose() => clock.Forget(this);

        public ValueTask DisposeAsync()
        {
            Dispose();
            return ValueTask.CompletedTask;
        }
    }
}
