# The Industry Is Catching Up: The Only Way to Generate AI Code That Works

Source: https://www.youtube.com/watch?v=EkH_uoybj8k

Auto-generated English captions.

I'm opinionated about lots of things, but particularly about software
development. And I'm rapidly coming to the conclusion that I know what the
future of AI assisted software development will probably look like. And it turns
out that lots of other people are coming to exactly the same conclusion. So,
it's possible that I and everyone else is on to something here. So, that's our
topic for today. Welcome to the modern software engineering channel. My name is
Dave Farley and if you haven't been here before, please do hit subscribe and if
you enjoy the content today, hit like as well. Bob Martin says he no longer
reads the code that his agents write. Instead, he surrounds the agents with
extreme constraints. Unit tests, girking tests, QA procedures, quality metrics,
and mutation testing. Adam Tornhill, after 25 years of test-driven development,
has dropped the fine grained red green refactor cycle for agent work, but kept
one vital rule. I always drive any change to the codebase via a failing test.
But his tests, just like mine, have moved up a level of abstraction. He now
defines them as specifications of end-to-end behavior rather than implementation
specific unit tests. I've been working this way driving development from BDD
star acceptance testdriven development for at least the last 20 years now. I
don't know if this was part of Adam's approach to TDD before this, but now these
specifications are the program for both of us. Sha Grove of Open AI stood on
stage at the AI engineer world's fair and told the room, "Make the specification
executable. feed the spec to the model and test against the spec. Kent Beck
calls TDD a superpower when working with AI agents. And Emily Beige says all the
tests together form the specification. Whoever happened to write each kind.
Anthropic's own guidance for clawed code puts it rather bluntly. If you can't
verify it, don't ship it. These people don't agree on everything. Some of them
don't agree with each other about very much at all. But they and I have arrived
mostly independently at the same conclusions. When a machine writes the code,
the human's job is to say precisely what the code should do in a form that can
be checked automatically. Not a prompt, not a markdown document, a specification
that runs and verifies that the system does what you want it to do. If you don't
know what you want it to do yet, you aren't really a programmer. you're just
along for the ride. So figuring out what we want it to do and verifying that it
does it is and to my mind always has been a fundamental core of our job as
programmers. I've been arguing for this for a long time. I call it acceptance
testdriven development and I was teaching this approach to development before
anyone outside of a research lab had even heard of large language models. What
interests me now though is not that I still think that this is a valuable
approach, though I do, but that this now seems to be an idea at the center of a
growing consensus. The people building and using these tools are rediscovering
this powerful intentbased approach to development for themselves. We may be
using different language to describe the same idea, but it is the same idea.
Programming has always encompassed three hard problems. We have to specify
precisely what it is that we want. We have to verify that we got what we wanted.
And we have to make progress in small steps. Small enough that we can tell when
we've gone off track and are heading in the wrong direction. Everything else is
really detail. AI changes the economics of exactly one activity producing the
code. It does nothing for these three though. To my mind, more foundational
harder problems. If anything, it makes each of them worse. A prompt is vagger
than a program and so more open to interpretation and more importantly
misinterpretation. A model will happily change more than you asked it to. So you
can't be certain that your system continues to do the things that it used to do
when you last checked. And a tool that produces a thousand lines a minute makes
it very tempting to take steps that are far too big. which means that changes
that you need to know about, good or bad, will be lost in the noise of the
changes that you don't care anything about. Steve YG says that he produces
12,000 lines of code a day with his agents. No human can review 12,000 lines a
day in any meaningful insightful way. So the interesting question is not really
how fast can we generate code. It's how fast can we know whether the code that
we produce is doing the right things. Danlu writing about running agents at
scale puts it well. Anything that's not well tested gets stochastically
degraded. Kent Beck puts it even better. When a tool claims to get 80% of a
payroll system done in one prompt, it may be right, but 80% of a payroll system
is the same thing as 0% of a payroll system. Verification is the bottleneck.
Now, one common response to this problem is we'll scale up by asking the AI to
write all of the tests. But if we ask the agent to write the tests after it's
written the code, the only input to those tests is the code. A test generated
from code can only confirm that the code does what it already does. It can't
tell us whether the code does something useful or does what we wanted it to do.
The intent has to come from somewhere else. It has to come from us and it has to
be in a form that we can use to measure the result to verify that we've actually
achieved our aim whatever that might be. The industry noticed this problem and
in 2025 specdriven development became a fashionable answer. GitHub released spec
kit and declared that the intent is the source of truth. Amazon built Kirao
around structured acceptance criteria. Tesla went further and proposed that the
spec, not the code, is the artifact that you maintain with the code as a
regeneratable output. Thoughtworks put the whole idea on their technology radar
to assess. I think these people are right about the diagnosis, but they miss
some things in the implementation. You can't steer an agent with vibes. Too
vague. You need a clear statement of what you want to achieve before the agent
starts. You also need that clear statement to survive after the agent has
finished. This is much better than describe your goal and get a big block of
code back that you must review manually. But look at what the specs are made of.
Markdown pros, structured pros in some cases, but pros all the same. And people
who tried these tools kept tripping over the same kinds of problems. Go Adzi,
who literally wrote the book on specification by example, tried spec kit and
found that the markdown spec lacked tons of detail. The real spec ends up being
in unit and integration tests. Burgittita Berkeler at ThoughtWorks worked with
three of these tools and reported that even with all of these files, templates,
prompts, workflows, and checklists, I frequently saw the agent ultimately not
follow all of the instructions. Colin Eberhart at Scott logic was bluntter code
is law because it's a formal language you can reason about you can test it you
can prove if it's right or wrong specifications or at least ones expressed in
the markdown format of a spec kit lack this formality that's the whole problem
in one paragraph a prospecification is a prompt with a longer word count an
agent can read it produce something that does not do what the spec says but the
agent doesn't tell you or even know that anything is wrong because nothing
fails. Nothing goes red, you're back to reading the code, crossing your fingers,
and hoping that everything will work out. It probably won't. Marcus is writing
for O'Reilly spotted the way out. Behavior-driven development, when done well,
collapses spec writing and spec validation into the same artifact. That's
exactly it. The specification and the validation that the code meets the
specification should be the same thing. When they are, the spec can't drift from
the code because the moment it does, the build breaks. An executable
specification is an example of the system doing something useful written in the
language of the problem domain. But it's also something that runs against the
real system and fails until the behavior described actually exists. Here's one.
Given a customer with a book in their basket, when they apply the discount code
summer, then the basket total is reduced by 10%. Notice what's not there.
There's no mention of HTTP, no buttons being pushed, no database tables, no
class names. It says what the system is meant to do and says nothing at all
about how it achieves that. That's not by accident. It's not style. That's the
entire point. A specification that describes the solution is not a
specification. It's a design. And it will break the moment somebody or something
finds a better design. This kind of behavioral specification is more deeply
true. It's true. Whatever solution we or our AI chooses to implement. It's true.
Even if we change something that makes the test fail, the test is now telling
us, screaming at us that your code isn't doing what you said it should. As long
as any implementation meets all of its specifications, that is passes all of the
executable tests that represent those specifications, it's valid as long as we
specify enough detail of what we want, I suppose. And when we don't, well,
that's the same as writing code in the old days. We learn from our mistake when
we discover it and we add more specifications as we would have added more code
in the olden days. Let me pause there and say thank you to our sponsors. We are
extremely fortunate to be sponsored by Equal Experts, Transfix, Octopus Deploy,
Zoo, and Smart Bear. Equal Experts is a multinational consultancy built on
applying the ideas and techniques that we talk about here to build great
software for their clients. Transfig is a financial technology company applying
advanced continuous delivery techniques to deliver low latency trade routting
services to some of the biggest financial institutions in the world. Octopus
deploy makes it easy to deliver software to Kubernetes, multicloud, on-prem
infrastructure and anywhere else. They automate the release, deployment, and
operations of your software and AI workloads with tools that handle continuous
delivery at scale. Zoo is a sidekick for your AI coding agent. It acts as an
architectural conscience and prevents structural erosion. It also helps clean up
legacy code bases with AI support. Smart Bear creates agentic QA for modern
software teams. Find real issues in minutes with QA agents that explore beyond
your existing tests and continuously validate your application as it changes.
All of these companies offer products and services that are extremely well
aligned with the topics that we discuss here on this channel every week. So if
you're looking for excellence in continuous delivery and software engineering in
general, do click on their links in the description below and when you talk to
them, mention that you found them from us. Thanks and back to the video. I think
that the consensus that I am describing at the start of this video is really
describing the next generation of programming. We shift from specifying a single
solution to specifying our intent to the system in enough detail to be able to
verify that we actually got what we wanted. Working this way means that it
doesn't matter if our AI rewrites the entire system underneath us as long as the
new version still passes all of its specifications. and so meets our behavioral
intent. To make an example like the one I showed earlier run, I and my AI
assistants build tests in four layers. The test case themselves are written in
the language of the problem domain. Below that sits a domain specific language
aimed at making the tests easy to write and consistent in execution. This DSL
turns behavioral ideas like apply the discount code into a reusable operation.
Protocol drivers sit below the DSL layer know how to talk to the real system
through its UI, its API or whatever else it exposes. So the final layer in this
stack is the system under test itself. The specification lives at the top. All
the technical coupling lives at the bottom. change the whole implementation,
swap the web framework, rewrite it in another language and the specification
still holds and the still tells you the truth of what your system is meant to be
doing. This is not a new idea. We built a complex sophisticated system this way
at Elmax in 2007 and are in tens of thousands of these specifications against
every commit. What is new is who benefits. The separation of what from how
inherent in this approach turns out to be precisely the contract an AI agent
needs. It then gets total freedom over how it implements things. But it gets no
freedom at all over what the system is meant to do. The spec is its fitness
function, the thing it must satisfy and the thing it is measured against. And
those things are the same artifact. Software development has always been a
translation. A vague wish becomes a user story. A story becomes a concrete
example. The example becomes executable specifications. And the specifications
become working software. Each step adds precision. And if you get stuck at any
step, that tells you something specific and important. If you can't think of an
example, you don't understand the problem well enough yet. What the agent does
is take the last step. The human directs things by owning the first three. This
is a big shift, but it is a shift in emphasis, not really in kind. We were
always supposed to be doing this as software developers. Many teams skipped it,
wrote code from the story directly and paid for it later. Now the cost of
skipping it is more immediate because the thing that writes the code has no idea
what you really meant. Follow these three practical rules and you will get
better results with AI assisted programming. Write the spec before the agent
starts. One scenario at a time. Watch it fail. Now, let the agent make it pass.
Read first is not ceremony. With an agent, red is the proof that your
specification is capable of catching a wrong answer. Keep the spec out of the
agents reach. Kent Beck is having trouble stopping AI agents from deleting tests
in order to make them pass. Emily Bash reports the same nasty habit of agents
deleting failing tests rather than fixing them. In this approach, the acceptance
tests are the contract. They are the program. Put them where the agent can't
edit them or treat every change to them as a change to the contract that a human
must approve. Bob Martin's agent swarm has a dedicated specifier role. I would
rather that role were a human or at the very least that a human signed off on
its output. Work in small steps one scenario red green review commit. This is
not because the agents need small steps for their own sake but because small
steps are how we find out where we are wrong while it's still cheap to be wrong.
If an agent produces 3,000 lines against a vague brief, it's taken one very
large step. And code review at that scale won't tell us if it was a good step or
a stumble. We need more robust verification than sh staring at thousands of
lines of code that something else wrote. This is still a version of specdriven
development and there are some objections to that. The most common criticism is
that this is waterfall in a trench code. If you write the entire spec for your
system up front as a markdown document, then that's a fair criticism. But this
is not true at all for acceptance test-driven development. One scenario is a few
lines. You write it, it goes red, the agent makes it go green, and then you
write the next specification. That's iteration and it is finer grain than most
teams manage today. But it is perfectly feasible, perfectly practical even for
very large, very complex systems. In fact, this kind of incrementalism is the
only way in practice to build large complex systems. But Gita Berkeler worried
that small work packages almost seem counter to the idea of spectriven
development. But small work packages are really the whole idea behind ATDD.
Emily Bash surveyed TDD practitioners working with agents and found that most of
them do read the code and worry about cognitive debt when they stop. Bob Martin
says he doesn't read it at all. I think I'm somewhere in between and I think
that it is a reasonable place to be. The executable specification doesn't stop
us reading the code. It makes reading it a choice that we take when the risks
warrant it rather than an obligation that we impose on ourselves to read every
line that the AI creates. It seems to me that this is the difference between a
practice that scales to meet the rate of AI code generation and one that does
not. Acceptance tests are slow, brittle, and assertion light. Sure, badly built
acceptance tests may be all of those things, and badly built acceptance tests
are worse than none. Martin Fowler is right to say that they are often not very
assertionheavy, giving us a false sense of security. It's certainly also true
that tests coupled to the UI break every time the UI changes. So my answer is
don't couple tests tightly to the UI. Do what I talked about, test cases, DSL,
protocol drivers. This is exactly what the four layer separation exists to fix.
And this is why I can see the value in pairing acceptance testing with mutation
testing as both Bob Martin and Martin Fowler recommend. If a mutant survives,
then your specification has a hole in it. If the AI writes the tests, it isn't
TDD, says Ian Cooper. He made that point years ago, and he was right. This is
why a human writes, or at least owns and approves the acceptance tests. The
agent can draft one. The agent can draft 10, but nothing counts as a
specification until a person, a human being who understands the problem says it
does. Specdriven development is acceptance testdriven development with the
executable part left out. But now the industry is seemingly catching up one blog
post at a time and seeing that the specification has to run. I'm glad. I would
rather people arrive at a good idea by a different route than not arrive at all.
But there is no need to reinvent it. The four-layer model, the language of the
problem domain, the discipline of red before green, the separation of what from
how. These all worked out, tested at scale and were written down years ago. They
were designed to control systems that changed underneath us and tell us the
truth about what was going on after every small change. It turns out that is
also exactly what we need to control an AI programming assistant. I've packaged
what I teach on all of this into an ATDD skill for AI coding agents. It walks
you through building the full layers of your own system and holds the agent to
those principles. If you've been vibe coding and wondering why the results are
hard to trust or you've adopted one of the spec driven tools and found the spec
drifting from the code, this is the missing piece. Vibe coding is not the best
that we can do. Neither is a markdown file with a spec in it. The spec must be
executable. Thank you all for watching and if you enjoy our content here on the
modern Sutter Engineering channel, why not consider supporting us by joining our
Patreon community? And to all our existing Patreons, thank you very much for
your support as ever and bye-bye.
