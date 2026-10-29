using JidokaUi.Core.Spend;

namespace JidokaUi.Tests.Spend;

public sealed class SpendAddressTests
{
    [Fact]
    public void NamesTheWeekAndTheGroupingAndReadsThemBack()
    {
        var address = SpendAddress.Of(new DateOnly(2026, 10, 19), SpendGrouping.Effort);

        Assert.Equal("spend?week=2026-10-19&by=effort", address);
        Assert.Equal(new DateOnly(2026, 10, 19), SpendAddress.WeekIn(address));
        Assert.Equal(SpendGrouping.Effort, SpendAddress.GroupingIn(address));
    }

    [Fact]
    public void ReadsADayThatIsNoMondayAsTheMondayOfItsWeek()
    {
        Assert.Equal(new DateOnly(2026, 10, 19), SpendAddress.WeekIn("spend?week=2026-10-25"));
    }

    [Theory]
    [InlineData("spend")]
    [InlineData("spend?week=last")]
    [InlineData("spend?week=2026-13-40")]
    [InlineData("spend?week=")]
    public void NamesNoWeekWhenTheAddressHoldsNoDate(string address)
    {
        Assert.Null(SpendAddress.WeekIn(address));
    }

    [Theory]
    [InlineData("spend")]
    [InlineData("spend?by=colour")]
    [InlineData("spend?by=Model")]
    public void NamesNoGroupingWhenTheAddressHoldsNoneThatTheLedgerHas(string address)
    {
        Assert.Null(SpendAddress.GroupingIn(address));
    }
}
