using Microsoft.Data.Sqlite;

namespace JidokaUi.Core.Spend;

/// <summary>
/// One row of jidoka's ledger: a worker run or a request of a manager, priced in dollars at list
/// price when jidoka wrote it.
/// </summary>
/// <param name="At">The second the row was written.</param>
/// <param name="Repo">The path of the repository's main worktree, which is a project path.</param>
/// <param name="Task">The task the run belongs to, or null for a run that belongs to none.</param>
/// <param name="Stage">The stage of the run, or manager for a request of a manager.</param>
/// <param name="Dollars">The price, or null when the model had no listed price.</param>
public sealed record LedgerRun(
    DateTimeOffset At,
    string Repo,
    string Epic,
    string? Task,
    string Stage,
    string? Track,
    string? Tier,
    string? Model,
    string? Effort,
    decimal? Dollars);

/// <summary>What a read of the ledger gave, or why it gave nothing.</summary>
/// <param name="Reason">Empty when the ledger answered; otherwise a message for the person.</param>
public sealed record LedgerRead(IReadOnlyList<LedgerRun> Runs, string Reason);

/// <summary>
/// jidoka's ledger, the SQLite file in its home. The app opens it read-only, because jidoka's
/// scripts are its only writer. A home with no ledger file has no spend yet, and the read leaves it
/// that way instead of creating the file.
/// </summary>
public sealed class Ledger
{
    private const string Select =
        "SELECT at, repo, epic, task, stage, track, tier, model, effort, dollars FROM runs ORDER BY id";

    private readonly string file;

    /// <param name="home">The home that holds the ledger file, as <see cref="Jidoka.JidokaHome"/> finds it.</param>
    public Ledger(Jidoka.JidokaHome home)
    {
        file = home.LedgerFile;
    }

    /// <summary>Every row of the ledger in the order jidoka wrote them.</summary>
    public LedgerRead Read()
    {
        if (!File.Exists(file))
        {
            return new LedgerRead([], string.Empty);
        }

        try
        {
            using var connection = new SqliteConnection(
                new SqliteConnectionStringBuilder
                {
                    DataSource = file,
                    Mode = SqliteOpenMode.ReadOnly,
                    Pooling = false,
                }.ToString());
            connection.Open();
            using var command = connection.CreateCommand();
            command.CommandText = Select;
            using var rows = command.ExecuteReader();
            var runs = new List<LedgerRun>();
            while (rows.Read())
            {
                runs.Add(new LedgerRun(
                    DateTimeOffset.FromUnixTimeSeconds(rows.GetInt64(0)),
                    rows.GetString(1),
                    rows.GetString(2),
                    TextOrNull(rows, 3),
                    rows.GetString(4),
                    TextOrNull(rows, 5),
                    TextOrNull(rows, 6),
                    TextOrNull(rows, 7),
                    TextOrNull(rows, 8),
                    rows.IsDBNull(9) ? null : Convert.ToDecimal(Math.Round(rows.GetDouble(9), 6))));
            }

            return new LedgerRead(runs, string.Empty);
        }
        catch (Exception unread) when (unread is SqliteException or InvalidOperationException or IOException)
        {
            return new LedgerRead([], $"The app could not read jidoka's ledger. {unread.Message}");
        }
    }

    private static string? TextOrNull(SqliteDataReader rows, int column) =>
        rows.IsDBNull(column) ? null : rows.GetString(column);
}
