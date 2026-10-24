using TracerUi.Web.Startup;

namespace TracerUi.Tests.Startup;

public sealed class BindAddressTests
{
    [Fact]
    public void BindsLoopbackWhenNoArgumentAsksForTheNetwork()
    {
        var address = BindAddress.From([]);

        Assert.Equal("http://localhost:5099", address.BoundAddress);
        Assert.False(address.ReachesEveryInterface);
    }

    [Fact]
    public void BindsEveryInterfaceWhenTheListenFlagIsPresent()
    {
        var address = BindAddress.From(["--listen"]);

        Assert.Equal("http://0.0.0.0:5099", address.BoundAddress);
        Assert.True(address.ReachesEveryInterface);
    }

    [Fact]
    public void ReadsTheListenFlagWhateverCaseItCarries()
    {
        Assert.True(BindAddress.From(["--LISTEN"]).ReachesEveryInterface);
    }

    [Theory]
    [InlineData("--listen=true")]
    [InlineData("/listen")]
    [InlineData("-listen")]
    public void RefusesAnArgumentThatOnlyLooksLikeTheListenFlag(string argument)
    {
        var refusal = Assert.Throws<ArgumentException>(() => BindAddress.From([argument]));

        Assert.Contains("--listen", refusal.Message);
    }

    [Fact]
    public void KeepsTheBrowserOnLoopbackInBothModes()
    {
        Assert.Equal("http://localhost:5099", BindAddress.From([]).BrowseAddress);
        Assert.Equal("http://localhost:5099", BindAddress.From(["--listen"]).BrowseAddress);
    }

    [Fact]
    public void BindsAndBrowsesThePortThatThePortFlagNames()
    {
        var address = BindAddress.From(["--port", "5101"]);

        Assert.Equal("http://localhost:5101", address.BoundAddress);
        Assert.Equal("http://localhost:5101", address.BrowseAddress);
        Assert.False(address.ReachesEveryInterface);
    }

    [Theory]
    [InlineData("--listen", "--port", "5101")]
    [InlineData("--port", "5101", "--listen")]
    public void BindsEveryInterfaceOnThePortThatThePortFlagNamesBesideTheListenFlag(
        string first, string second, string third)
    {
        var address = BindAddress.From([first, second, third]);

        Assert.Equal("http://0.0.0.0:5101", address.BoundAddress);
        Assert.Equal("http://localhost:5101", address.BrowseAddress);
        Assert.True(address.ReachesEveryInterface);
    }

    [Fact]
    public void ReadsThePortFlagWhateverCaseItCarries()
    {
        Assert.Equal(5101, BindAddress.From(["--PORT", "5101"]).Port);
    }

    [Theory]
    [InlineData("1", 1)]
    [InlineData("65535", 65535)]
    public void TakesEveryPortFromOneTo65535(string value, int port)
    {
        Assert.Equal(port, BindAddress.From(["--port", value]).Port);
    }

    [Theory]
    [InlineData("0")]
    [InlineData("65536")]
    [InlineData("99999999999")]
    [InlineData("+5101")]
    [InlineData("-5101")]
    [InlineData("05101")]
    [InlineData(" 5101")]
    [InlineData("5101 ")]
    [InlineData("5_101")]
    [InlineData("٥١٠١")]
    [InlineData("")]
    [InlineData("web")]
    [InlineData("--listen")]
    public void RefusesAValueAfterThePortFlagThatIsNotAPortNumber(string value)
    {
        var refusal = Assert.Throws<ArgumentException>(() => BindAddress.From(["--port", value]));

        Assert.Contains($"the port {value}.", refusal.Message);
        Assert.Contains("--port 5101", refusal.Message);
    }

    [Fact]
    public void RefusesThePortFlagWithNoValueAfterIt()
    {
        var refusal = Assert.Throws<ArgumentException>(() => BindAddress.From(["--listen", "--port"]));

        Assert.Contains("no port after --port", refusal.Message);
        Assert.Contains("--port 5101", refusal.Message);
    }

    [Theory]
    [InlineData("--port=5101")]
    [InlineData("/port")]
    [InlineData("-port")]
    [InlineData("--ports")]
    public void RefusesAnArgumentThatOnlyLooksLikeThePortFlag(string argument)
    {
        var refusal = Assert.Throws<ArgumentException>(() => BindAddress.From([argument, "5101"]));

        Assert.Contains($"the argument {argument}.", refusal.Message);
        Assert.Contains("--port 5101", refusal.Message);
    }

    [Theory]
    [InlineData("5101")]
    [InlineData("5102")]
    public void RefusesThePortFlagThatAppearsMoreThanOnce(string secondPort)
    {
        var refusal = Assert.Throws<ArgumentException>(
            () => BindAddress.From(["--port", "5101", "--port", secondPort]));

        Assert.Contains("--port appears more than once", refusal.Message);
    }
}
