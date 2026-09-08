namespace TracerUi.Core.Beads;

/// <summary>
/// The type words that bd itself ships. A project can configure more of them, and this class does
/// not know those, so a type that this bd refuses comes back as a message from bd and not as an
/// error of the app.
/// </summary>
public static class BeadType
{
    public const string Bug = "bug";

    public const string Feature = "feature";

    public const string Task = "task";

    public const string Epic = "epic";

    public const string Chore = "chore";

    public const string Decision = "decision";

    /// <summary>The word of one type that bd ships, the machine form that a write of the type carries.</summary>
    public static string Word(this BeadTypeWord type) => type switch
    {
        BeadTypeWord.Bug => Bug,
        BeadTypeWord.Feature => Feature,
        BeadTypeWord.Task => Task,
        BeadTypeWord.Epic => Epic,
        BeadTypeWord.Chore => Chore,
        BeadTypeWord.Decision => Decision,
        _ => throw new ArgumentOutOfRangeException(nameof(type), type, "This type has no word."),
    };

    /// <summary>The type that this word names, or none when it names none of the six.</summary>
    public static bool TryParse(string word, out BeadTypeWord type) =>
        EnumWord.TryParse(word, Word, out type);
}

/// <summary>One of the type words that bd itself ships, so a write can carry no other of them.</summary>
public enum BeadTypeWord
{
    Bug,
    Feature,
    Task,
    Epic,
    Chore,
    Decision,
}
