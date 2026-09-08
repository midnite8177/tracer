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
}
