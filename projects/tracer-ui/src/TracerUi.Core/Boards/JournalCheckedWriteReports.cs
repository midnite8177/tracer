namespace TracerUi.Core.Boards;

/// <summary>
/// The reports of a watch, with a journal check beside it. FSEvents, which the watch of .NET uses
/// on macOS, reports some writes seconds late and drops others, so the check reads the total size
/// of the Dolt journals under .beads at each interval. It reports a write when that total changes,
/// or when the journals appear or go away, and it runs no bd. A report of the watch counts as a
/// write only when the total changed since the check last read it, so the check never reports one
/// write twice. Where .beads holds no journal, every report of the watch passes through.
/// </summary>
/// <remarks>
/// The check reads the size and not the modified time, because every read of bd rewrites the
/// modified time of the journal. A read of bd rewrites other files under .beads too, and the watch
/// reports those as it reports a write. Only a write changes the size.
/// </remarks>
public sealed class JournalCheckedWriteReports : IWriteReports
{
    /// <summary>
    /// The name of the chunk journal of a Dolt database, the file that every write appends to.
    /// </summary>
    public const string JournalFileName = "vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv";

    /// <summary>
    /// How often the check reads the journal. A board trails a write that the file system did not
    /// report by about this much, plus the quiet period of the project watcher and one read of bd.
    /// </summary>
    public static readonly TimeSpan Interval = TimeSpan.FromSeconds(1);

    private readonly IWriteReports watch;
    private readonly TimeProvider clock;
    private readonly TimeSpan interval;

    public JournalCheckedWriteReports(IWriteReports watch, TimeProvider clock, TimeSpan interval)
    {
        this.watch = watch;
        this.clock = clock;
        this.interval = interval;
    }

    public IDisposable Start(string directory, Action wrote, Action lostReports)
    {
        var check = new Check(directory, wrote);
        var reports = watch.Start(directory, check.WatchReported, lostReports);
        var timer = clock.CreateTimer(_ => check.CompareTheJournal(), null, interval, interval);
        return new Running(check, timer, reports);
    }

    private sealed class Check
    {
        private readonly string directory;
        private readonly Action wrote;

        // Ticks of the timer overlap when a read of the disk is slow, and a report of the watch can
        // arrive during a tick; without the gate both could see one change and report it twice.
        private readonly Lock gate = new();
        private JournalReading lastReading;
        private bool stopped;

        public Check(string directory, Action wrote)
        {
            this.directory = directory;
            this.wrote = wrote;
            lastReading = ReadTheJournal();
        }

        public void WatchReported()
        {
            lock (gate)
            {
                if (stopped)
                {
                    return;
                }

                var reading = ReadTheJournal();

                // Without a journal the watch alone follows the project, so every report of it
                // counts; comparing sizes there would leave the board with no live updates.
                if (JournalChanged(reading) || reading is JournalReading.NoJournal)
                {
                    wrote();
                }
            }
        }

        public void CompareTheJournal()
        {
            lock (gate)
            {
                if (!stopped && JournalChanged(ReadTheJournal()))
                {
                    wrote();
                }
            }
        }

        public void Stop()
        {
            lock (gate)
            {
                stopped = true;
            }
        }

        private bool JournalChanged(JournalReading reading)
        {
            if (reading is JournalReading.Unreadable || reading == lastReading)
            {
                return false;
            }

            lastReading = reading;
            return true;
        }

        private JournalReading ReadTheJournal()
        {
            var databases = Path.Combine(directory, "embeddeddolt");
            if (!Directory.Exists(databases))
            {
                return new JournalReading.NoJournal();
            }

            try
            {
                var journals = Directory.EnumerateDirectories(databases)
                    .Select(database => new FileInfo(Path.Combine(database, ".dolt", "noms", JournalFileName)))
                    .Where(journal => journal.Exists)
                    .ToList();
                return journals.Count == 0
                    ? new JournalReading.NoJournal()
                    : new JournalReading.Sized(journals.Sum(journal => journal.Length));
            }
            catch (Exception reading) when (reading is IOException or UnauthorizedAccessException)
            {
                return new JournalReading.Unreadable();
            }
        }
    }

    private abstract record JournalReading
    {
        // .beads holds no Dolt journal, so its size cannot tell a read of bd from a write.
        public sealed record NoJournal : JournalReading;

        // The total size of the journals under .beads.
        public sealed record Sized(long Size) : JournalReading;

        // The directory could not be read, which says nothing about a write.
        public sealed record Unreadable : JournalReading;
    }

    private sealed class Running(Check check, ITimer timer, IDisposable reports) : IDisposable
    {
        public void Dispose()
        {
            check.Stop();
            timer.Dispose();
            reports.Dispose();
        }
    }
}
