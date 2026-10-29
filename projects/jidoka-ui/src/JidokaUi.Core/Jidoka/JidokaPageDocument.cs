using System.Net;
using System.Text.RegularExpressions;

namespace JidokaUi.Core.Jidoka;

/// <summary>One stretch of the body of a jidoka page: plain markup, or a slot that the app fills.</summary>
/// <param name="Html">The HTML of the stretch, exactly as the script wrote it.</param>
public abstract record PagePart(string Html);

/// <summary>A stretch of the body that holds no slot, which the app shows as it is.</summary>
public sealed record PageMarkup(string Html) : PagePart(Html);

/// <summary>
/// An element that the page marks with <c>data-jidoka-slot</c>, where the app draws a control. The
/// html is the whole element, the placeholder text that the script wrote in it included, so a slot
/// the app draws nothing in shows what the page said.
/// </summary>
/// <param name="Name">The value of the attribute, such as <c>answer-panel</c>.</param>
/// <param name="Html">The whole element, from its start tag to its end tag.</param>
public sealed record PageSlot(string Name, string Html) : PagePart(Html);

/// <summary>
/// A jidoka page cut into the parts that the app draws: its title, its stylesheet scoped to the
/// element that holds the page, and its body split at every slot. jidoka writes the pages from
/// fixed templates, so the cut reads their tags and does not parse HTML in general.
/// </summary>
/// <param name="Title">The text of the title element, or an empty string when the page has none.</param>
/// <param name="Style">The stylesheet, nested in <c>.jidoka-page</c>, or an empty string when the page has none.</param>
/// <param name="Parts">The body in order, split at every slot.</param>
public sealed record JidokaPageDocument(string Title, string Style, IReadOnlyList<PagePart> Parts)
{
    /// <summary>The class of the element that holds a page, which the scoped stylesheet names.</summary>
    public const string HolderClass = "jidoka-page";

    private const string SlotAttribute = "data-jidoka-slot";

    private static readonly Regex TitleElement = new(
        @"<title[^>]*>(?<text>.*?)</title>", RegexOptions.IgnoreCase | RegexOptions.Singleline | RegexOptions.CultureInvariant);

    private static readonly Regex StyleElement = new(
        @"<style[^>]*>(?<css>.*?)</style>", RegexOptions.IgnoreCase | RegexOptions.Singleline | RegexOptions.CultureInvariant);

    private static readonly Regex BodyElement = new(
        @"<body[^>]*>(?<inner>.*)</body>", RegexOptions.IgnoreCase | RegexOptions.Singleline | RegexOptions.CultureInvariant);

    private static readonly Regex SlotStart = new(
        $@"<(?<tag>[a-zA-Z][a-zA-Z0-9]*)\b[^>]*\b{SlotAttribute}=""(?<name>[^""]*)""[^>]*>",
        RegexOptions.CultureInvariant);

    private static readonly Regex RootOrBodySelector = new(
        @"(?<![\w.#-])(:root|body)(?![\w-])", RegexOptions.CultureInvariant);

    /// <summary>Cuts a page into the parts that the app draws.</summary>
    public static JidokaPageDocument Parse(string html)
    {
        var title = TitleElement.Match(html) is { Success: true } found
            ? WebUtility.HtmlDecode(found.Groups["text"].Value).Trim()
            : string.Empty;
        var css = string.Join(
            "\n",
            StyleElement.Matches(html).Select(style => style.Groups["css"].Value.Trim()).Where(text => text.Length > 0));
        var body = BodyElement.Match(html) is { Success: true } inside ? inside.Groups["inner"].Value : html;
        return new JidokaPageDocument(title, Scoped(css), PartsOf(body));
    }

    private static string Scoped(string css) =>
        css.Length == 0
            ? string.Empty
            : $".{HolderClass} {{\n{RootOrBodySelector.Replace(css, "&")}\n}}";

    private static List<PagePart> PartsOf(string body)
    {
        var parts = new List<PagePart>();
        var position = 0;
        while (SlotStart.Match(body, position) is { Success: true } start)
        {
            var end = EndOfElement(body, start);
            AddMarkup(parts, body[position..start.Index]);
            parts.Add(new PageSlot(start.Groups["name"].Value, body[start.Index..end]));
            position = end;
        }

        AddMarkup(parts, body[position..]);
        return parts;
    }

    private static void AddMarkup(List<PagePart> parts, string html)
    {
        if (!string.IsNullOrWhiteSpace(html))
        {
            parts.Add(new PageMarkup(html));
        }
    }

    private static int EndOfElement(string body, Match start)
    {
        var tag = Regex.Escape(start.Groups["tag"].Value);
        var tags = new Regex($@"<(?<close>/?){tag}\b[^>]*?(?<selfClosed>/?)>", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
        var depth = start.Value.EndsWith("/>", StringComparison.Ordinal) ? 0 : 1;
        var position = start.Index + start.Length;
        while (depth > 0 && tags.Match(body, position) is { Success: true } next)
        {
            depth += next.Groups["close"].Length > 0 ? -1 : next.Groups["selfClosed"].Length > 0 ? 0 : 1;
            position = next.Index + next.Length;
        }

        return depth > 0 ? body.Length : position;
    }
}
