using System.Globalization;
using TracerUi.Core.Beads;

namespace TracerUi.Core.Boards;

/// <summary>
/// One comment on a bead. The comments are the work journal, so the detail page shows them in the
/// order that bd prints them, each with the moment that its author wrote it.
/// </summary>
/// <param name="At">The moment, or null when bd printed none that the app could read.</param>
/// <param name="RawTimestamp">What bd printed for the moment, whether or not it is a time.</param>
public sealed record BeadComment(string Author, string Text, DateTimeOffset? At, string RawTimestamp)
{
    // How the detail page writes a moment. A moment that the app could not read stands as bd printed it.
    private const string Format = "yyyy-MM-dd HH:mm";

    public string Timestamp =>
        At is { } moment ? moment.ToLocalTime().ToString(Format, CultureInfo.InvariantCulture) : RawTimestamp;

    public static BeadComment From(BeadRecord record)
    {
        var raw = record.Text(BeadFields.CreatedOfAComment);
        return new BeadComment(
            record.Text(BeadFields.AuthorOfAComment),
            record.Text(BeadFields.TextOfAComment),
            MomentIn(raw),
            raw);
    }

    private static DateTimeOffset? MomentIn(string raw) =>
        DateTimeOffset.TryParse(
            raw,
            CultureInfo.InvariantCulture,
            DateTimeStyles.RoundtripKind,
            out var moment)
            ? moment
            : null;
}
