namespace JidokaUi.Core.Spend;

/// <summary>A column of the ledger that the spend view can group the cost by.</summary>
public enum SpendGrouping
{
    /// <summary>The grade of worker that the stage asked for.</summary>
    Tier,

    /// <summary>The model that ran.</summary>
    Model,

    /// <summary>The effort of the route.</summary>
    Effort,

    /// <summary>The simple track or the full track of the task's lap.</summary>
    Track,
}

/// <summary>The words that name the groupings, in the address and on the page.</summary>
public static class SpendGroupings
{
    /// <summary>The word for a run that has no value in the column, such as a request of a manager.</summary>
    public const string NoValue = "none";

    /// <summary>The word that the address and the page use for this grouping.</summary>
    public static string Word(this SpendGrouping by) => by switch
    {
        SpendGrouping.Tier => "tier",
        SpendGrouping.Model => "model",
        SpendGrouping.Effort => "effort",
        SpendGrouping.Track => "track",
        _ => throw new ArgumentOutOfRangeException(nameof(by), by, "The ledger has no such column."),
    };

    /// <summary>Reads a word, such as one from an address. It gives false for a word that names no grouping.</summary>
    public static bool TryFrom(string? word, out SpendGrouping by)
    {
        foreach (var candidate in Enum.GetValues<SpendGrouping>())
        {
            if (string.Equals(candidate.Word(), word, StringComparison.Ordinal))
            {
                by = candidate;
                return true;
            }
        }

        by = default;
        return false;
    }

    /// <summary>The value of this run in the column, or <see cref="NoValue"/> when the run has none.</summary>
    public static string ValueOf(this SpendGrouping by, LedgerRun run) =>
        (by switch
        {
            SpendGrouping.Tier => run.Tier,
            SpendGrouping.Model => run.Model,
            SpendGrouping.Effort => run.Effort,
            SpendGrouping.Track => run.Track,
            _ => throw new ArgumentOutOfRangeException(nameof(by), by, "The ledger has no such column."),
        }) is { Length: > 0 } value ? value : NoValue;
}
