using TracerUi.Core.Projects;

namespace TracerUi.Web.Components.Pages;

/// <summary>
/// Where a switch walks from the page on the screen. A page that shows one project says where, and
/// the project picker asks, so the picker knows no page by name. On a page that said nothing, a
/// pick makes the project active and stays. One lives per circuit, because each tab stands on its
/// own page.
/// </summary>
public sealed class SwitchAddress
{
    private Walk? current;

    /// <summary>
    /// Makes a switch walk to the address that this gives for the picked project, until the page
    /// disposes what this returns. A page that arrives replaces the one it leaves before that one
    /// is disposed, so the dispose clears only a walk that is still its own.
    /// </summary>
    public IDisposable WalkTo(Func<ProjectPath, string> addressOf)
    {
        var walk = new Walk(this, addressOf);
        current = walk;
        return walk;
    }

    /// <summary>The address that a switch to this project walks to, or null on a page that said nothing.</summary>
    public string? For(ProjectPath project) => current?.AddressOf(project);

    private sealed class Walk : IDisposable
    {
        private readonly SwitchAddress owner;

        public Walk(SwitchAddress owner, Func<ProjectPath, string> addressOf)
        {
            this.owner = owner;
            AddressOf = addressOf;
        }

        public Func<ProjectPath, string> AddressOf { get; }

        public void Dispose()
        {
            if (ReferenceEquals(owner.current, this))
            {
                owner.current = null;
            }
        }
    }
}
