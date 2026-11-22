export const lapGuardCases = {
  "commands": [
    "dotnet build App.slnx",
    "TMPDIR=/tmp python3 tests/run_suite.py",
    "dotnet test App.slnx",
    "cd app && pytest",
    "echo $(id)",
    "head",
    "grep",
    { "command": "git add", "then": "paths" },
    { "command": "git rebase --abort", "then": "nothing" },
    { "command": "git log", "then": "words", "refusing": ["--output"] },
    { "command": "git grep", "then": "words", "refusing": ["--open-files-in-pager", "-O"] }
  ],
  "barred": ["specs/acceptance"],
  "cases": [
    {
      "name": "ACommandOnTheListIsAllowed",
      "kind": "lap",
      "call": "dotnet build App.slnx",
      "verdict": { "decision": "allow" }
    },
    {
      "name": "ACommandOnTheListMayTakeAnyWordsAfterIt",
      "kind": "lap",
      "call": "dotnet test App.slnx --filter FullyQualifiedName~Card",
      "verdict": { "decision": "allow" }
    },
    {
      "name": "AnEntryThatSpellsAVariableAllowsTheCommandSpelledTheSameWay",
      "kind": "lap",
      "call": "TMPDIR=/tmp python3 tests/run_suite.py -k test_card",
      "verdict": { "decision": "allow" }
    },
    {
      "name": "ACommandOffTheListIsDeniedWithItsReason",
      "kind": "lap",
      "call": "curl https://example.com",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `curl https://example.com` is off jidoka's lists for lap workers. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "ACommandThatOnlyStartsLikeAListedOneIsDenied",
      "kind": "lap",
      "call": "dotnet testing App.slnx",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `dotnet testing App.slnx` is off jidoka's lists for lap workers. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "ASequenceOfListedCommandsIsAllowed",
      "kind": "lap",
      "call": "dotnet build App.slnx && dotnet test App.slnx",
      "verdict": { "decision": "allow" }
    },
    {
      "name": "ASequenceWithOneCommandOffTheListIsDeniedAsAWhole",
      "kind": "lap",
      "call": "dotnet build App.slnx && curl https://example.com",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `dotnet build App.slnx && curl https://example.com` is off jidoka's lists for lap workers. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "APipeOfListedCommandsIsAllowed",
      "kind": "lap",
      "call": "grep -rn Card src | head -n 5",
      "verdict": { "decision": "allow" }
    },
    {
      "name": "EachCommandOfATextEntryThatHoldsTwoIsListed",
      "kind": "lap",
      "call": "cd app",
      "verdict": { "decision": "allow" }
    },
    {
      "name": "EachCommandOfATextEntryThatHoldsTwoIsListedWithWordsAfterIt",
      "kind": "lap",
      "call": "pytest -x",
      "verdict": { "decision": "allow" }
    },
    {
      "name": "ATextEntryThatCannotBeSplitAddsNothingToTheList",
      "kind": "lap",
      "call": "echo hi",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `echo hi` is off jidoka's lists for lap workers. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "ACommandSubstitutionIsDenied",
      "kind": "lap",
      "call": "dotnet build $(whoami)",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `dotnet build $(whoami)` is off jidoka's lists for lap workers. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "ABacktickSubstitutionIsDenied",
      "kind": "lap",
      "call": "dotnet build `whoami`",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `dotnet build `whoami`` is off jidoka's lists for lap workers. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "AProcessSubstitutionIsDenied",
      "kind": "lap",
      "call": "grep a <(ls)",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `grep a <(ls)` is off jidoka's lists for lap workers. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "ARedirectIntoAFileIsDenied",
      "kind": "lap",
      "call": "dotnet test App.slnx > out.txt",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `dotnet test App.slnx > out.txt` is off jidoka's lists for lap workers. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "AnAppendIntoAFileIsDenied",
      "kind": "lap",
      "call": "dotnet test App.slnx >> out.txt",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `dotnet test App.slnx >> out.txt` is off jidoka's lists for lap workers. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "ARedirectToTheNullDeviceIsAllowed",
      "kind": "lap",
      "call": "dotnet test App.slnx > /dev/null 2>&1",
      "verdict": { "decision": "allow" }
    },
    {
      "name": "ADuplicationOfOneStreamOntoAnotherIsAllowed",
      "kind": "lap",
      "call": "dotnet test App.slnx 2>&1 | head",
      "verdict": { "decision": "allow" }
    },
    {
      "name": "AnUnclosedQuoteIsDenied",
      "kind": "lap",
      "call": "dotnet build 'App.slnx",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `dotnet build 'App.slnx` is off jidoka's lists for lap workers. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "QuotesAreTakenOffTheWordsBeforeTheListIsRead",
      "kind": "lap",
      "call": "dotnet 'build' \"App.slnx\"",
      "verdict": { "decision": "allow" }
    },
    {
      "name": "AnEscapedSpaceMakesOneWord",
      "kind": "lap",
      "call": "dotnet\\ build App.slnx",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `dotnet\\ build App.slnx` is off jidoka's lists for lap workers. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "ACommandBehindAVariableThatNoListSetsIsDenied",
      "kind": "lap",
      "call": "FOO=1 dotnet build App.slnx",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `FOO=1 dotnet build App.slnx` is off jidoka's lists for lap workers. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "AnEmptyCommandIsDenied",
      "kind": "lap",
      "call": "",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `` is off jidoka's lists for lap workers. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "AnEntryThatAllowsNothingAfterItAllowsTheCommandAlone",
      "kind": "lap",
      "call": "git rebase --abort",
      "verdict": { "decision": "allow" }
    },
    {
      "name": "AnEntryThatAllowsNothingAfterItDeniesAnyWordAfterIt",
      "kind": "lap",
      "call": "git rebase --abort --quiet",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `git rebase --abort --quiet` is off jidoka's lists for lap workers. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "AnEntryThatAllowsPathsAllowsPathsAfterIt",
      "kind": "lap",
      "call": "git add src/a.py src/b.py",
      "verdict": { "decision": "allow" }
    },
    {
      "name": "AnEntryThatAllowsPathsDeniesAnOptionAfterIt",
      "kind": "lap",
      "call": "git add -A",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `git add -A` is off jidoka's lists for lap workers. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "AnEntryThatAllowsPathsDoesNotReadWhatFollowsTheDoubleDash",
      "kind": "lap",
      "call": "git add -- -A",
      "verdict": { "decision": "allow" }
    },
    {
      "name": "AnEntryThatRefusesAnOptionAllowsOtherWords",
      "kind": "lap",
      "call": "git log --oneline -n 5",
      "verdict": { "decision": "allow" }
    },
    {
      "name": "AnEntryThatRefusesAnOptionDeniesItSpelledInFull",
      "kind": "lap",
      "call": "git log --output=out.txt",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `git log --output=out.txt` is off jidoka's lists for lap workers. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "AnEntryThatRefusesAnOptionDeniesItAbbreviated",
      "kind": "lap",
      "call": "git log --out=out.txt",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `git log --out=out.txt` is off jidoka's lists for lap workers. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "AnEntryThatRefusesAShortOptionDeniesItInABundle",
      "kind": "lap",
      "call": "git grep -nO Card",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `git grep -nO Card` is off jidoka's lists for lap workers. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "AnEntryThatRefusesAShortOptionAllowsOtherShortOptions",
      "kind": "lap",
      "call": "git grep -n Card",
      "verdict": { "decision": "allow" }
    },
    {
      "name": "ACheckWorkerMayRunAListedCommand",
      "kind": "check",
      "call": "dotnet build App.slnx",
      "verdict": { "decision": "allow" }
    },
    {
      "name": "ACheckWorkerIsDeniedACommandOffTheListInTheWordsOfItsStage",
      "kind": "check",
      "call": "curl https://example.com",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `curl https://example.com` is off jidoka's lists for check workers. Find another way, or report the holdout you could not test as failed, saying that this call was denied."
      }
    },
    {
      "name": "AWriteInsideTheWorktreeIsAllowed",
      "kind": "lap",
      "use": { "tool": "write", "path": "{worktree}/src/a.py" },
      "verdict": { "decision": "allow" }
    },
    {
      "name": "AnEditInsideTheWorktreeIsAllowed",
      "kind": "lap",
      "use": { "tool": "edit", "path": "{worktree}/src/a.py" },
      "verdict": { "decision": "allow" }
    },
    {
      "name": "ANotebookEditInsideTheWorktreeIsAllowed",
      "kind": "lap",
      "use": { "tool": "edit_notebook", "path": "{worktree}/nb.ipynb" },
      "verdict": { "decision": "allow" }
    },
    {
      "name": "AWriteOfAFileNotMadeYetInsideTheWorktreeIsAllowed",
      "kind": "lap",
      "use": { "tool": "write", "path": "{worktree}/src/new/deep/a.py" },
      "verdict": { "decision": "allow" }
    },
    {
      "name": "AWriteOutsideTheWorktreeIsDeniedWithItsPlace",
      "kind": "lap",
      "use": { "tool": "write", "path": "{outside}/a.py" },
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: {tool} of {outside}/a.py is outside the lap's worktree {worktree}."
      }
    },
    {
      "name": "AnEditOutsideTheWorktreeIsDenied",
      "kind": "lap",
      "use": { "tool": "edit", "path": "{outside}/a.py" },
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: {tool} of {outside}/a.py is outside the lap's worktree {worktree}."
      }
    },
    {
      "name": "ANotebookEditOutsideTheWorktreeIsDenied",
      "kind": "lap",
      "use": { "tool": "edit_notebook", "path": "{outside}/nb.ipynb" },
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: {tool} of {outside}/nb.ipynb is outside the lap's worktree {worktree}."
      }
    },
    {
      "name": "AWriteThatClimbsOutOfTheWorktreeIsDenied",
      "kind": "lap",
      "use": { "tool": "write", "path": "{worktree}/src/../../outside/a.py" },
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: {tool} of {worktree}/src/../../outside/a.py is outside the lap's worktree {worktree}."
      }
    },
    {
      "name": "AWriteIntoAFolderThatOnlyStartsLikeTheWorktreeIsDenied",
      "kind": "lap",
      "use": { "tool": "write", "path": "{worktree}-old/a.py" },
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: {tool} of {worktree}-old/a.py is outside the lap's worktree {worktree}."
      }
    },
    {
      "name": "AWriteThroughALinkThatLeadsOutOfTheWorktreeIsDenied",
      "kind": "lap",
      "links": { "{worktree}/out": "{outside}" },
      "use": { "tool": "write", "path": "{worktree}/out/a.py" },
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: {tool} of {worktree}/out/a.py is outside the lap's worktree {worktree}."
      }
    },
    {
      "name": "AWriteOfTheWorktreeItselfIsDenied",
      "kind": "lap",
      "use": { "tool": "write", "path": "{worktree}" },
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: {tool} of {worktree} is outside the lap's worktree {worktree}."
      }
    },
    {
      "name": "AWriteInsideAnAcceptanceFolderIsDeniedWithTheWayToAskForAChange",
      "kind": "lap",
      "use": { "tool": "write", "path": "{worktree}/specs/acceptance/a.md" },
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: {tool} of {worktree}/specs/acceptance/a.md is inside the acceptance folder specs/acceptance, which only the spec task's lap may change. If a spec looks wrong, park the task with a question that says which spec and why."
      }
    },
    {
      "name": "AnEditInsideAnAcceptanceFolderIsDenied",
      "kind": "lap",
      "use": { "tool": "edit", "path": "{worktree}/specs/acceptance/a.md" },
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: {tool} of {worktree}/specs/acceptance/a.md is inside the acceptance folder specs/acceptance, which only the spec task's lap may change. If a spec looks wrong, park the task with a question that says which spec and why."
      }
    },
    {
      "name": "AWriteBesideAnAcceptanceFolderIsAllowed",
      "kind": "lap",
      "use": { "tool": "write", "path": "{worktree}/specs/other.md" },
      "verdict": { "decision": "allow" }
    },
    {
      "name": "AReadIsAllowedAnywhere",
      "kind": "lap",
      "use": { "tool": "read", "path": "{outside}/notes.md" },
      "verdict": { "decision": "allow" }
    },
    {
      "name": "AStartOfAWorkerIsDenied",
      "kind": "lap",
      "use": { "tool": "start_workers" },
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: a lap worker starts no workers, so its {tool} call is denied."
      }
    },
    {
      "name": "ADefinitionOfAWorkerIsDenied",
      "kind": "lap",
      "use": { "tool": "define_workers" },
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: a lap worker starts no workers, so its {tool} call is denied."
      }
    },
    {
      "name": "ALiveQuestionFromALapWorkerIsDeniedWithTheWayToAskInstead",
      "kind": "lap",
      "use": { "tool": "ask" },
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: a lap worker never asks live. End the stage with a question report in the scratch folder and the outcome question."
      }
    },
    {
      "name": "ALiveQuestionFromACheckWorkerIsDeniedWithTheWayToReportInstead",
      "kind": "check",
      "use": { "tool": "ask" },
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: a check worker never asks live. Say what you could not test in your report."
      }
    },
    {
      "name": "AToolNoRuleKnowsIsDeniedWithItsName",
      "kind": "lap",
      "use": { "tool": "Teleport" },
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: Teleport is off jidoka's lists for lap workers. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "AToolNoRuleKnowsIsDeniedToACheckWorkerInTheWordsOfItsStage",
      "kind": "check",
      "use": { "tool": "Teleport" },
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: Teleport is off jidoka's lists for check workers. Find another way, or report the holdout you could not test as failed, saying that this call was denied."
      }
    },
    {
      "name": "ADeleteOfAFileInsideTheWorktreeIsAllowed",
      "kind": "lap",
      "call": "rm src/a.py",
      "verdict": { "decision": "allow" }
    },
    {
      "name": "ADeleteWithOnlyTheOptionsFAndRIsAllowed",
      "kind": "lap",
      "call": "rm -rf build obj",
      "verdict": { "decision": "allow" }
    },
    {
      "name": "AGitRmWithOnlyItsAllowedOptionsIsAllowed",
      "kind": "lap",
      "call": "git rm -r --cached src/a.py",
      "verdict": { "decision": "allow" }
    },
    {
      "name": "ADeleteOutsideTheWorktreeIsDeniedWithItsPlace",
      "kind": "lap",
      "call": "rm {outside}/a.py",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `rm {outside}/a.py` deletes outside the lap's worktree {worktree}. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "ADeleteThatClimbsOutOfTheWorktreeIsDenied",
      "kind": "lap",
      "call": "rm ../outside/a.py",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `rm ../outside/a.py` deletes outside the lap's worktree {worktree}. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "ADeleteThroughALinkThatLeadsOutOfTheWorktreeIsDenied",
      "kind": "lap",
      "links": { "{worktree}/out": "{outside}" },
      "call": "rm out/a.py",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `rm out/a.py` deletes outside the lap's worktree {worktree}. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "ADeleteOfTheWorktreeItselfIsDenied",
      "kind": "lap",
      "call": "rm -rf .",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `rm -rf .` deletes outside the lap's worktree {worktree}. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "ADeleteWhosePathsAreAGlobIsDeniedAsOneJidokaCannotTell",
      "kind": "lap",
      "call": "rm src/*.py",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `rm src/*.py` is a delete whose paths jidoka cannot tell: a lap worker may delete only paths it names one by one, with no option but -f and -r (git rm: -r, -q and --cached), no glob, variable or `~`, no variable set in front of it, and no change of folder before it. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "ADeleteAfterAChangeOfFolderIsDeniedAsOneJidokaCannotTell",
      "kind": "lap",
      "call": "cd app && rm a.py",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `cd app && rm a.py` is a delete whose paths jidoka cannot tell: a lap worker may delete only paths it names one by one, with no option but -f and -r (git rm: -r, -q and --cached), no glob, variable or `~`, no variable set in front of it, and no change of folder before it. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "ADeleteWithAnOptionOtherThanFAndRIsDeniedAsOneJidokaCannotTell",
      "kind": "lap",
      "call": "rm -i src/a.py",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `rm -i src/a.py` is a delete whose paths jidoka cannot tell: a lap worker may delete only paths it names one by one, with no option but -f and -r (git rm: -r, -q and --cached), no glob, variable or `~`, no variable set in front of it, and no change of folder before it. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "ADeleteInsideAnAcceptanceFolderIsDenied",
      "kind": "lap",
      "call": "rm specs/acceptance/a.md",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `rm specs/acceptance/a.md` is inside the acceptance folder specs/acceptance, which only the spec task's lap may change. If a spec looks wrong, park the task with a question that says which spec and why."
      }
    },
    {
      "name": "ADeleteOfAFolderThatHoldsAnAcceptanceFolderIsDenied",
      "kind": "lap",
      "call": "rm -r specs",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `rm -r specs` holds the acceptance folder specs/acceptance, which only the spec task's lap may change. If a spec looks wrong, park the task with a question that says which spec and why."
      }
    },
    {
      "name": "ADeleteOneCheckWorkerMakesIsOffTheLists",
      "kind": "check",
      "call": "rm src/a.py",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `rm src/a.py` is off jidoka's lists for check workers. Find another way, or report the holdout you could not test as failed, saying that this call was denied."
      }
    },
    {
      "name": "AFolderMadeWithMkdirPInsideTheWorktreeIsAllowed",
      "kind": "lap",
      "call": "mkdir -p src/new/deep",
      "verdict": { "decision": "allow" }
    },
    {
      "name": "AFolderMadeOutsideTheWorktreeIsDeniedWithItsPlace",
      "kind": "lap",
      "call": "mkdir -p {outside}/new",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `mkdir -p {outside}/new` makes a folder or moves a file outside the lap's worktree {worktree}. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "AFolderMadeInsideAnAcceptanceFolderIsDenied",
      "kind": "lap",
      "call": "mkdir -p specs/acceptance/new",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `mkdir -p specs/acceptance/new` is inside the acceptance folder specs/acceptance, which only the spec task's lap may change. If a spec looks wrong, park the task with a question that says which spec and why."
      }
    },
    {
      "name": "AMkdirWithAnOptionOtherThanPIsOffTheLists",
      "kind": "lap",
      "call": "mkdir -m 777 src/new",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `mkdir -m 777 src/new` is off jidoka's lists for lap workers. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "AMoveBetweenPathsInsideTheWorktreeIsAllowed",
      "kind": "lap",
      "call": "mv -f src/a.py src/b.py",
      "verdict": { "decision": "allow" }
    },
    {
      "name": "AGitMvBetweenPathsInsideTheWorktreeIsAllowed",
      "kind": "lap",
      "call": "git mv src/a.py src/b.py",
      "verdict": { "decision": "allow" }
    },
    {
      "name": "AMoveToAPlaceOutsideTheWorktreeIsDeniedWithItsPlace",
      "kind": "lap",
      "call": "mv src/a.py {outside}/a.py",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `mv src/a.py {outside}/a.py` makes a folder or moves a file outside the lap's worktree {worktree}. Find another way, or park the task with a question that names this call."
      }
    },
    {
      "name": "AMoveOutOfAnAcceptanceFolderIsDenied",
      "kind": "lap",
      "call": "mv specs/acceptance/a.md src/a.md",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `mv specs/acceptance/a.md src/a.md` is inside the acceptance folder specs/acceptance, which only the spec task's lap may change. If a spec looks wrong, park the task with a question that says which spec and why."
      }
    },
    {
      "name": "AMoveIntoAnAcceptanceFolderIsDenied",
      "kind": "lap",
      "call": "mv src/a.py specs/acceptance",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `mv src/a.py specs/acceptance` is inside the acceptance folder specs/acceptance, which only the spec task's lap may change. If a spec looks wrong, park the task with a question that says which spec and why."
      }
    },
    {
      "name": "AMoveOfAFolderThatHoldsAnAcceptanceFolderIsDenied",
      "kind": "lap",
      "call": "mv specs archived-specs",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `mv specs archived-specs` holds the acceptance folder specs/acceptance, which only the spec task's lap may change. If a spec looks wrong, park the task with a question that says which spec and why."
      }
    },
    {
      "name": "AMoveWithAnOptionOtherThanFIsOffTheLists",
      "kind": "lap",
      "call": "mv -n src/a.py src/b.py",
      "verdict": {
        "decision": "deny",
        "reason": "jidoka: `mv -n src/a.py src/b.py` is off jidoka's lists for lap workers. Find another way, or park the task with a question that names this call."
      }
    }
  ]
}
