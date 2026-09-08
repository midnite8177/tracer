namespace TracerUi.Core.Projects;

/// <summary>Decides whether a directory on disk is a project that the app can open.</summary>
public static class ProjectPathValidator
{
    /// <summary>The directory that marks a repository as a beads project.</summary>
    public const string BeadsDirectoryName = ".beads";

    public static ProjectPathValidation Validate(string candidatePath)
    {
        if (string.IsNullOrWhiteSpace(candidatePath))
        {
            return ProjectPathValidation.Invalid("Select a directory first.");
        }

        if (!Directory.Exists(candidatePath))
        {
            return ProjectPathValidation.Invalid("This directory does not exist.");
        }

        if (!Directory.Exists(Path.Combine(candidatePath, BeadsDirectoryName)))
        {
            return ProjectPathValidation.Invalid(
                $"This directory has no {BeadsDirectoryName} directory, so it is not a beads project.");
        }

        return ProjectPathValidation.Valid();
    }
}
