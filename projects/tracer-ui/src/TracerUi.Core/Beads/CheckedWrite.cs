namespace TracerUi.Core.Beads;

/// <summary>A parse of an enum's word, in the shape that an <c>out</c> parameter takes.</summary>
public delegate bool WordParser<T>(string word, out T value)
    where T : struct, Enum;

/// <summary>Runs a write only once its word parses, and reports a message from the person instead when it does not.</summary>
public static class CheckedWrite
{
    public static Task<BdWriteOutcome> Async<T>(
        string value,
        WordParser<T> parse,
        Func<T, Task<BdWriteOutcome>> write,
        string failureMessage)
        where T : struct, Enum =>
        parse(value, out var parsed)
            ? write(parsed)
            : Task.FromResult(BdWriteOutcome.Failure(failureMessage));

    public static Task<BdWriteOutcome> Async(
        string value,
        Func<BeadLabel, Task<BdWriteOutcome>> write,
        string failureMessage) =>
        BeadLabel.TryFrom(value, out var label)
            ? write(label)
            : Task.FromResult(BdWriteOutcome.Failure(failureMessage));
}
