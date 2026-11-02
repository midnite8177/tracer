using JidokaUi.Core.Beads;

namespace JidokaUi.Core.Jidoka;

/// <summary>
/// Launches the Python that jidoka's settings name, with a script of jidoka as its first argument. It
/// starts the program the way <see cref="BdProcess"/> does, because a script and bd both give an exit
/// code and two streams, and the failure of a program that is missing reads the same for both.
/// </summary>
public sealed class JidokaProcess : IJidokaProcess
{
    public Task<BdResult> RunAsync(
        string program, string workingDirectory, IReadOnlyList<string> arguments, CancellationToken stop) =>
        new BdProcess(program).RunAsync(workingDirectory, arguments, stop);
}
