namespace TracerUi.Core.Projects;

/// <summary>The outcome of a check of a candidate project path.</summary>
/// <param name="IsValid">True when the path names a project that the app can open.</param>
/// <param name="Message">Empty when the path is valid; otherwise the reason it is not.</param>
public sealed record ProjectPathValidation(bool IsValid, string Message)
{
    public static ProjectPathValidation Valid() => new(true, string.Empty);

    public static ProjectPathValidation Invalid(string message) => new(false, message);
}
