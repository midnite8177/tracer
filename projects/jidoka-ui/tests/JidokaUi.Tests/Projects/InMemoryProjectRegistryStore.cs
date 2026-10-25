using JidokaUi.Core.Projects;

namespace JidokaUi.Tests.Projects;

/// <summary>A registry store that a test drives without a file on disk.</summary>
public sealed class InMemoryProjectRegistryStore : IProjectRegistryStore
{
    private readonly Lock guard = new();
    private ProjectRegistry registry = ProjectRegistry.Empty;
    private int saves;
    private bool busy;

    /// <summary>How many times the code under test wrote a registry.</summary>
    public int Saves
    {
        get
        {
            lock (guard)
            {
                return saves;
            }
        }
    }

    /// <summary>
    /// True while another copy of the app holds the registry, so that every update answers busy and
    /// changes nothing.
    /// </summary>
    public bool Busy
    {
        get
        {
            lock (guard)
            {
                return busy;
            }
        }
        set
        {
            lock (guard)
            {
                busy = value;
            }
        }
    }

    /// <summary>Puts this registry in the store, as a write from outside the code under test would.</summary>
    public void Hold(ProjectRegistry registry)
    {
        lock (guard)
        {
            this.registry = registry;
        }
    }

    public ProjectRegistry Load()
    {
        lock (guard)
        {
            return registry;
        }
    }

    public RegistryUpdate Update(Func<ProjectRegistry, ProjectRegistry?> change)
    {
        lock (guard)
        {
            if (busy)
            {
                return RegistryUpdate.Busy;
            }

            if (change(registry) is not { } changed)
            {
                return RegistryUpdate.Unchanged;
            }

            registry = changed;
            saves++;
            return RegistryUpdate.Written;
        }
    }
}
