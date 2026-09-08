using TracerUi.Core.Beads;
using TracerUi.Core.Boards;

namespace TracerUi.Tests.Beads;

public sealed class BeadWriteChoicesTests
{
    [Fact]
    public void OffersTheFourStoredStatusesBecauseAPersonAsksOneQuestionAboutTheStateOfABead()
    {
        Assert.Equal(
            [StoredStatus.Open, StoredStatus.InProgress, StoredStatus.Deferred, StoredStatus.Closed],
            BeadWriteChoices.Statuses);
    }

    [Fact]
    public void OffersNoEpicTypeToQuickCreateBecauseAnEpicNeedsTheWriteThatStartsIt()
    {
        Assert.DoesNotContain(BeadWriteChoices.EpicType, BeadWriteChoices.QuickCreateTypes);
        Assert.Contains(BeadWriteChoices.EpicType, BeadWriteChoices.Types);
        Assert.Contains("task", BeadWriteChoices.QuickCreateTypes);
    }
}
