using JidokaUi.Core.Projects;

namespace JidokaUi.Tests.Projects;

/// <summary>A jidoka that has onboarded no repo, for a test whose subject is the registry.</summary>
public sealed class NoOnboardedProjects : IOnboardedProjects
{
    public IReadOnlyList<ProjectPath> Paths() => [];
}
