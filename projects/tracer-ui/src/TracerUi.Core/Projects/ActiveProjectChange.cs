namespace TracerUi.Core.Projects;

/// <summary>Where a change of the active project came from.</summary>
public enum ActiveProjectChangeKind
{
    /// <summary>A person picked another project in the top bar.</summary>
    Switch,

    /// <summary>The browser gave a session back the project that it already held.</summary>
    Restore,
}

/// <summary>
/// A change of the active project, and where it came from. A page that leaves on a switch stays
/// where it stands on a restore, because the person asked for nothing.
/// </summary>
/// <param name="Project">The project that is active now.</param>
/// <param name="Kind">Whether a person made this change, or the browser did.</param>
public sealed record ActiveProjectChange(ProjectPath Project, ActiveProjectChangeKind Kind);
