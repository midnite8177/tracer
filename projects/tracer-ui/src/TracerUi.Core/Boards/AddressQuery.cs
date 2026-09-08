namespace TracerUi.Core.Boards;

/// <summary>
/// The names and the values of the query of an address. A name without a value states nothing, and a
/// name that appears twice keeps its first value, so one name always answers with one value. Every
/// address of the app reads its parts here, so one rule reads them all.
/// </summary>
internal static class AddressQuery
{
    public static IReadOnlyDictionary<string, string> Of(string address)
    {
        var query = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        var mark = address.IndexOf('?', StringComparison.Ordinal);
        if (mark < 0)
        {
            return query;
        }

        foreach (var pair in address[(mark + 1)..].Split('&', StringSplitOptions.RemoveEmptyEntries))
        {
            var equals = pair.IndexOf('=', StringComparison.Ordinal);
            if (equals <= 0)
            {
                continue;
            }

            var name = Uri.UnescapeDataString(pair[..equals]);
            if (!query.ContainsKey(name))
            {
                query[name] = Uri.UnescapeDataString(pair[(equals + 1)..]);
            }
        }

        return query;
    }
}
