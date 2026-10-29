using System.Globalization;
using JidokaUi.Core.Boards;

namespace JidokaUi.Core.Spend;

/// <summary>
/// The address of the spend view. It carries the week and the grouping, so a reload shows the same
/// figures and a link can name last week's cost per merged task by model.
/// </summary>
public static class SpendAddress
{
    /// <summary>The page that every spend address names.</summary>
    public const string Page = "spend";

    /// <summary>The name of the query part that holds the Monday of the week.</summary>
    public const string WeekQueryName = "week";

    /// <summary>The name of the query part that holds the grouping.</summary>
    public const string GroupQueryName = "by";

    private const string DateFormat = "yyyy-MM-dd";

    /// <summary>The address of the spend view for this week, grouped this way.</summary>
    public static string Of(DateOnly week, SpendGrouping by) =>
        $"{Page}?{WeekQueryName}={DayText(week)}&{GroupQueryName}={by.Word()}";

    /// <summary>The day as the address writes it and the page shows it, the same in every culture.</summary>
    public static string DayText(DateOnly day) => day.ToString(DateFormat, CultureInfo.InvariantCulture);

    /// <summary>
    /// The Monday of the week that this address names, or null when it names none or names a day
    /// that is no date. A day that is not a Monday names the week that holds it.
    /// </summary>
    public static DateOnly? WeekIn(string address) =>
        AddressQuery.Of(address).TryGetValue(WeekQueryName, out var text)
        && DateOnly.TryParseExact(text, DateFormat, CultureInfo.InvariantCulture, DateTimeStyles.None, out var day)
            ? SpendReader.WeekOf(day)
            : null;

    /// <summary>The grouping that this address names, or null when it names none that the ledger has.</summary>
    public static SpendGrouping? GroupingIn(string address) =>
        AddressQuery.Of(address).TryGetValue(GroupQueryName, out var word) && SpendGroupings.TryFrom(word, out var by)
            ? by
            : null;
}

/// <summary>How the spend view writes a sum of dollars.</summary>
public static class SpendMoney
{
    /// <summary>The dollars with a dollar sign and two decimals, the same in every culture.</summary>
    public static string Text(decimal dollars) =>
        string.Create(CultureInfo.InvariantCulture, $"${dollars:F2}");
}
