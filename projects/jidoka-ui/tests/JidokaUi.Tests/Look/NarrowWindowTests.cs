using System.Globalization;
using System.Text.RegularExpressions;
using JidokaUi.Tests.Startup;

namespace JidokaUi.Tests.Look;

/// <summary>
/// What the stylesheets give a window as narrow as a phone, 390 pixels wide, where the needs-you view
/// and the answer panel must work. No test lays out a page, so these read the rules that the app
/// serves in the bundle of the component stylesheets: a rule that a rename or a deletion loses is a
/// phone that scrolls sideways again.
/// </summary>
public sealed partial class NarrowWindowTests
{
    private const int TheWidthOfAPhone = 390;
    private const string TheComponentStylesheets = "/JidokaUi.Web.styles.css";

    [Fact]
    public async Task StacksTheNeedsYouTableIntoOneColumnInAWindowAsNarrowAsAPhone()
    {
        var rules = await TheRulesOfAWindowAsNarrowAsAPhoneAsync();

        Assert.Contains(rules, rule => rule.Selects("needs-you-table") && rule.Declares("display: block"));
    }

    [Fact]
    public async Task LeavesTheProjectOfARowToTheHeadingAboveTheTableInAWindowAsNarrowAsAPhone()
    {
        var rules = await TheRulesOfAWindowAsNarrowAsAPhoneAsync();

        Assert.Contains(rules, rule => rule.Selects("needs-you-project-cell") && rule.Declares("display: none"));
    }

    [Fact]
    public async Task GivesTheAnswerOfARowTheWholeWidthInAWindowAsNarrowAsAPhone()
    {
        var rules = await TheRulesOfAWindowAsNarrowAsAPhoneAsync();

        Assert.Contains(rules, rule => rule.Selects("needs-you-answer-cell") && rule.Declares("display: block"));
    }

    [Fact]
    public async Task MakesEachAnswerAPressAsWideAsThePanelAndAsTallAsAFingertipInAWindowAsNarrowAsAPhone()
    {
        var rules = await TheRulesOfAWindowAsNarrowAsAPhoneAsync();

        Assert.Contains(
            rules,
            rule => rule.Selects("answer-press") && rule.Declares("flex: 1 1 100%") && rule.Declares("min-height:"));
    }

    [Fact]
    public async Task WrapsTheNavLinksOfTheTopBarInAWindowAsNarrowAsAPhone()
    {
        var rules = await TheRulesOfAWindowAsNarrowAsAPhoneAsync();

        Assert.Contains(rules, rule => rule.Selects("top-bar-nav") && rule.Declares("flex-wrap: wrap"));
    }

    private static async Task<IReadOnlyList<NarrowRule>> TheRulesOfAWindowAsNarrowAsAPhoneAsync()
    {
        using var app = new AnAppOverHttp();
        using var browser = app.CreateClient();
        var stylesheets = await browser.GetStringAsync(TheComponentStylesheets) + await browser.GetStringAsync("/app.css");

        var rules = new List<NarrowRule>();
        foreach (Match media in AMaxWidthMediaBlock().Matches(stylesheets))
        {
            var width = int.Parse(media.Groups["width"].Value, CultureInfo.InvariantCulture);
            if (width >= TheWidthOfAPhone)
            {
                rules.AddRange(RulesIn(TheBlockAfter(stylesheets, media.Index + media.Length)));
            }
        }

        return rules;
    }

    private static string TheBlockAfter(string stylesheets, int start)
    {
        var depth = 1;
        for (var index = start; index < stylesheets.Length; index++)
        {
            depth += stylesheets[index] switch
            {
                '{' => 1,
                '}' => -1,
                _ => 0,
            };
            if (depth == 0)
            {
                return stylesheets[start..index];
            }
        }

        throw new InvalidOperationException("A media block of the stylesheets never closes.");
    }

    private static IEnumerable<NarrowRule> RulesIn(string block) =>
        block.Split('}', StringSplitOptions.RemoveEmptyEntries)
            .Select(rule => rule.Split('{'))
            .Where(parts => parts.Length == 2)
            .Select(parts => new NarrowRule(WithoutComments(parts[0]), WithoutComments(parts[1])));

    private static string WithoutComments(string text) => AComment().Replace(text, string.Empty).Trim();

    [GeneratedRegex(@"@media\s*\(\s*max-width:\s*(?<width>\d+)px\s*\)\s*\{")]
    private static partial Regex AMaxWidthMediaBlock();

    [GeneratedRegex(@"/\*.*?\*/", RegexOptions.Singleline)]
    private static partial Regex AComment();

    private sealed record NarrowRule(string Selector, string Declarations)
    {
        public bool Selects(string className) =>
            Regex.IsMatch(Selector, $@"\.{Regex.Escape(className)}(?![\w-])");

        public bool Declares(string declaration) =>
            Regex.Replace(Declarations, @"\s+", " ").Contains(declaration, StringComparison.Ordinal);
    }
}
