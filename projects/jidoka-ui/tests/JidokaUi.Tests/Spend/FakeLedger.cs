using JidokaUi.Core.Spend;
using Microsoft.Data.Sqlite;

namespace JidokaUi.Tests.Spend;

/// <summary>
/// The ledger file that jidoka's ledger script keeps in its home, written by hand with the same
/// table, so that a test reads what the real file holds without starting Python.
/// </summary>
public sealed class FakeLedger
{
    private const string Schema =
        """
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at INTEGER NOT NULL,
            repo TEXT NOT NULL,
            epic TEXT NOT NULL,
            task TEXT,
            lap INTEGER,
            stage TEXT NOT NULL,
            try_number INTEGER,
            track TEXT,
            tier TEXT,
            harness TEXT,
            model TEXT,
            effort TEXT,
            agent TEXT,
            input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            cache_read_tokens INTEGER NOT NULL,
            cache_write_tokens INTEGER NOT NULL,
            dollars REAL,
            wall_seconds INTEGER NOT NULL,
            outcome TEXT NOT NULL
        )
        """;

    /// <param name="home">The folder that stands for jidoka's home.</param>
    public FakeLedger(string home)
    {
        File = Path.Combine(home, "ledger.sqlite");
    }

    /// <summary>The path of the ledger file.</summary>
    public string File { get; }

    /// <summary>Writes one run of a worker, as the ledger script writes it.</summary>
    public FakeLedger Ran(LedgerRun run)
    {
        using var connection = new SqliteConnection($"Data Source={File};Pooling=False");
        connection.Open();
        using (var create = connection.CreateCommand())
        {
            create.CommandText = Schema;
            create.ExecuteNonQuery();
        }

        using var insert = connection.CreateCommand();
        insert.CommandText =
            """
            INSERT INTO runs (at, repo, epic, task, stage, track, tier, model, effort, input_tokens, output_tokens,
                              cache_read_tokens, cache_write_tokens, dollars, wall_seconds, outcome)
            VALUES ($at, $repo, $epic, $task, $stage, $track, $tier, $model, $effort, 0, 0, 0, 0, $dollars, 0, 'done')
            """;
        insert.Parameters.AddWithValue("$at", run.At.ToUnixTimeSeconds());
        insert.Parameters.AddWithValue("$repo", run.Repo);
        insert.Parameters.AddWithValue("$epic", run.Epic);
        insert.Parameters.AddWithValue("$task", (object?)run.Task ?? DBNull.Value);
        insert.Parameters.AddWithValue("$stage", run.Stage);
        insert.Parameters.AddWithValue("$track", (object?)run.Track ?? DBNull.Value);
        insert.Parameters.AddWithValue("$tier", (object?)run.Tier ?? DBNull.Value);
        insert.Parameters.AddWithValue("$model", (object?)run.Model ?? DBNull.Value);
        insert.Parameters.AddWithValue("$effort", (object?)run.Effort ?? DBNull.Value);
        insert.Parameters.AddWithValue("$dollars", run.Dollars is { } dollars ? (object)(double)dollars : DBNull.Value);
        insert.ExecuteNonQuery();
        return this;
    }
}
