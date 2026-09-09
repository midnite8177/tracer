namespace TracerUi.Web.Components.Layout;

/// <summary>
/// Whether a mark should show, for a state that a component starts and stops. It shows only once
/// the state has lasted longer than the wait, and once shown it stays for at least the floor, so a
/// state that ends just after the mark appears does not blink it off the screen. The working mark
/// and the re-read mark both render from one of these, so the wait and the floor mean the same
/// thing on both.
/// </summary>
public sealed class DelayedMark : IDisposable
{
    private readonly TimeProvider clock;
    private readonly TimeSpan wait;
    private readonly TimeSpan floor;
    private readonly Func<Task> changed;

    private bool active;
    private DateTimeOffset? shownAt;
    private CancellationTokenSource? pending;

    public DelayedMark(TimeProvider clock, TimeSpan wait, TimeSpan floor, Func<Task> changed)
    {
        this.clock = clock;
        this.wait = wait;
        this.floor = floor;
        this.changed = changed;
    }

    public bool Visible => shownAt is not null;

    /// <summary>Starts or stops the state that the mark answers for.</summary>
    public void SetActive(bool active)
    {
        if (active == this.active)
        {
            return;
        }

        this.active = active;
        pending?.Cancel();
        pending = new CancellationTokenSource();

        if (active)
        {
            // A zero-delay Task.Delay still costs a render cycle, so a mark with no wait to serve
            // would stand one frame late if it went through the same path as a delayed one.
            if (wait <= TimeSpan.Zero)
            {
                shownAt = clock.GetUtcNow();
            }
            else
            {
                _ = ShowOnceTheWaitElapsesAsync(pending.Token);
            }
        }
        else if (shownAt is { } shown)
        {
            _ = HideOnceTheFloorElapsesAsync(shown, pending.Token);
        }
    }

    private async Task ShowOnceTheWaitElapsesAsync(CancellationToken cancellation)
    {
        try
        {
            await Task.Delay(wait, clock, cancellation);
        }
        catch (OperationCanceledException)
        {
            return;
        }

        shownAt = clock.GetUtcNow();
        await changed();
    }

    private async Task HideOnceTheFloorElapsesAsync(DateTimeOffset shown, CancellationToken cancellation)
    {
        var remaining = floor - (clock.GetUtcNow() - shown);
        if (remaining > TimeSpan.Zero)
        {
            try
            {
                await Task.Delay(remaining, clock, cancellation);
            }
            catch (OperationCanceledException)
            {
                return;
            }
        }

        shownAt = null;
        await changed();
    }

    public void Dispose() => pending?.Cancel();
}
