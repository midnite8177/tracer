using System.Text.Json;
using JidokaUi.Core.Beads;

namespace JidokaUi.Core.Jidoka;

/// <summary>One value of a rules setting: the JSON that the rules script takes, and the text that a person reads.</summary>
public sealed record RuleValue(string Json, string Text)
{
    internal static RuleValue Of(JsonElement element) =>
        new(element.GetRawText(), JsonText.Of(element));
}

/// <summary>
/// One setting of an epic's factory rules that a person picks from a list, as the rules script lists
/// it: its name, the values it takes, and the value the epic holds, or null when it holds none.
/// </summary>
public sealed record RuleSetting(string Name, IReadOnlyList<RuleValue> Choices, RuleValue? Value)
{
    /// <summary>True when the epic holds this choice.</summary>
    public bool Holds(RuleValue choice) => Value is { } held && held.Json == choice.Json;
}

/// <summary>One setting to change, by the name and the JSON value that the rules script takes.</summary>
public sealed record RuleChange(string Name, RuleValue Value)
{
    internal string Argument => $"{Name}={Value.Json}";
}
