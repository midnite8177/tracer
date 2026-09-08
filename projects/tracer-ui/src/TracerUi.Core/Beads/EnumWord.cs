namespace TracerUi.Core.Beads;

/// <summary>Parses the machine word of one enum value, matched against every value's word.</summary>
public static class EnumWord
{
    public static bool TryParse<TEnum>(string word, Func<TEnum, string> wordOf, out TEnum value)
        where TEnum : struct, Enum
    {
        foreach (var candidate in Enum.GetValues<TEnum>())
        {
            if (wordOf(candidate) == word)
            {
                value = candidate;
                return true;
            }
        }

        value = default;
        return false;
    }
}
