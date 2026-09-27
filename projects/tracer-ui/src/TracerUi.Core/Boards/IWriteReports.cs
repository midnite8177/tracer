namespace TracerUi.Core.Boards;

/// <summary>
/// The reports of the writes under a directory: a report of a write, and a signal that reports
/// were dropped.
/// </summary>
public interface IWriteReports
{
    /// <summary>
    /// Starts the reports of writes under this directory and its subdirectories. It calls
    /// <paramref name="wrote"/> for each write that it reports, and <paramref name="lostReports"/>
    /// when it dropped reports that it could not hold, and it goes on reporting after that. The
    /// two callbacks stay apart so that a caller can tell a write from a loss. Both run on a thread
    /// of the reports, where a throw ends the app. The directory must exist. Disposing the result
    /// stops the reports.
    /// </summary>
    IDisposable Start(string directory, Action wrote, Action lostReports);
}
