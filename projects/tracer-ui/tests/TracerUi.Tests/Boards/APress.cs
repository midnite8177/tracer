using AngleSharp.Dom;
using Bunit;
using Microsoft.AspNetCore.Components.Web;
using TracerUi.Core.Boards;

namespace TracerUi.Tests.Boards;

/// <summary>
/// A press on a row, as a browser reports it. The row component, the board and the needs-you view
/// each answer to the same press, so one type says where a press lands, what its release carries,
/// and how far it travels before a row reads it as a drag.
/// </summary>
public static class APress
{
    // Where a press goes down and comes up when the press is a click and not a drag.
    private const double WhereItLands = 100;

    /// <summary>
    /// How far a press travels when a person drags across the text of a row. It stands above
    /// RowPress.DragDistance, so a row reads a press that travels this far as a drag.
    /// </summary>
    public const double TheTravelOfADrag = 60;

    /// <summary>
    /// How far a press travels when the hand that holds the mouse moves a little. It stands under
    /// RowPress.DragDistance, so a row reads a press that travels this far as a click.
    /// </summary>
    public const double TheTravelOfAClick = 2;

    /// <summary>The release of a press that carries no key, which opens the bead in this tab.</summary>
    public static MouseEventArgs Plain => new()
    {
        ClientX = WhereItLands,
        ClientY = WhereItLands,
    };

    /// <summary>The release of the middle button, which asks for a new tab and carries no key.</summary>
    public static MouseEventArgs OfTheMiddleButton => new()
    {
        ClientX = WhereItLands,
        ClientY = WhereItLands,
        Button = RowRelease.MiddleButton,
    };

    /// <summary>The release that carries the meta key, which a browser reads as a new tab.</summary>
    public static MouseEventArgs CarryingTheMetaKey => new()
    {
        ClientX = WhereItLands,
        ClientY = WhereItLands,
        MetaKey = true,
    };

    /// <summary>
    /// The release that carries the control key, which a browser reads as a new tab everywhere
    /// but on a Mac.
    /// </summary>
    public static MouseEventArgs CarryingTheControlKey => new()
    {
        ClientX = WhereItLands,
        ClientY = WhereItLands,
        CtrlKey = true,
    };

    /// <summary>
    /// The release of a press that traveled this far to the right of it. It carries the button and
    /// every modifier key of the press, so a release says the same thing wherever it lands.
    /// </summary>
    public static MouseEventArgs Beside(MouseEventArgs press, double travel) => new()
    {
        ClientX = press.ClientX + travel,
        ClientY = press.ClientY,
        Button = press.Button,
        AltKey = press.AltKey,
        CtrlKey = press.CtrlKey,
        MetaKey = press.MetaKey,
        ShiftKey = press.ShiftKey,
    };

    /// <summary>
    /// Presses a row and releases it where the press started, so the press is a click and not a
    /// drag. The release states the button and the keys that the browser reports.
    /// </summary>
    public static void LandsOn(Func<IElement> row, MouseEventArgs release) =>
        TravelsAcross(row, release, release);

    public static void DragsAcross(Func<IElement> row, MouseEventArgs press) =>
        TravelsAcross(row, press, Beside(press, TheTravelOfADrag));

    /// <summary>
    /// Presses a row and releases it, as a browser does: the mouse goes down, it comes up, and the
    /// click follows it. A view draws its rows again after each event, so each one asks for the
    /// row again.
    /// </summary>
    public static void TravelsAcross(Func<IElement> row, MouseEventArgs press, MouseEventArgs release)
    {
        GoesDownOn(row, press);
        row().MouseUp(release);
        row().Click(release);
    }

    /// <summary>
    /// Presses a row and clicks where the press went down, with no release of the mouse between
    /// them. The click is the event that opens the bead, so a test of that path alone sends the
    /// two on their own. The click lands on the element that the caller names, because a press on
    /// the title of a row clicks the title and presses the row that holds it.
    /// </summary>
    public static void GoesDownAndClicksOn(
        Func<IElement> row, Func<IElement> clicked, MouseEventArgs press)
    {
        GoesDownOn(row, press);
        clicked().Click(press);
    }

    /// <summary>Puts the mouse down where the press started, and does not release it.</summary>
    public static void GoesDownOn(Func<IElement> row, MouseEventArgs press) =>
        row().MouseDown(new MouseEventArgs { ClientX = press.ClientX, ClientY = press.ClientY });
}
