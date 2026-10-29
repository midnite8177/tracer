namespace JidokaUi.Core.Projects;

/// <summary>The repos that jidoka onboarded on this machine, which the app lists beside its own registry.</summary>
public interface IOnboardedProjects
{
    /// <summary>The main worktree of every repo that jidoka holds settings for.</summary>
    IReadOnlyList<ProjectPath> Paths();
}
