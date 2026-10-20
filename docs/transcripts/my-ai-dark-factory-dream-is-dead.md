# My AI Dark Factory Dream Is Dead (Here's What Actually Works)

Source: https://www.youtube.com/watch?v=GQatuTWSRqY

Auto-generated English captions.

The AI dark factory is the most autonomous form of agentic engineering. We give
it some kind of higher-level document for an epic or release, and it figures
out how to build and validate everything and ship it straight to production. If
this could be reliable, it would be the dream for building any software. But,
to be a bit dramatic for effect, my hopes and dreams have been crushed here. As
I've been experimenting building my own dark factory, I've come to the
conclusion this is just simply not the way to do things. But, what is actually
working for me, what I've turned this into, doesn't have to be that much
different. I'm not actually losing that much autonomy. And so, that's what I
want to cover with you right now. And let me tell you, it has been a
fascinating journey to get to where I am now. There's so many lessons I want to
share with you in this video for why the dark factory doesn't work and why what
I'm building now actually does. And so, for the dark factory, even if we had
AGI and the best LLMs in the world, this still wouldn't work. We need a system
that looks more like this. And yeah, I know, it looks complicated, but I'll
break it down nice and simple for you right now. And it's important to
understand this kind of workflow because, let's face it, the way we work with
coding agents, even in the next 6 months, isn't going to look the same. Because
as harnesses and LLMs get better and better, we need to give them more autonomy
if we want to ship faster. And so, I truly believe in the next couple of years
every person and company is going to be moving towards a system that looks like
this. And even if you don't want to go and build a full AI software factory
right now, which yes, that is different than a dark factory, it's still good to
see what the full process looks like. There's a lot of lessons I have built in
here that you can even just incorporate for your current agentic coding
workflows. But overall, this is how I'm seeing the industry converge. As I work
with companies and build this sort of thing, talk to people that are creating
their own, everyone is building a system that is becoming more and more similar
over time. So, this really is the future. This is the next step for agentic
engineering. Okay, so before I get into anything else, I need to cover why the
dark factory doesn't work as much as I wish it did. And so, the number one goal
here is plain and simple. We just want to make our coding agents as autonomous
as possible. Now, it's not vibe coding because we're putting a lot of effort up
front engineering our harness. And so, yeah, we're trusting the agent at
runtime when it's building the software, but it's only because we put a lot of
our engineering effort into setting it up for success. And so, we define the
exact process it goes through as it builds everything. Now, for my own dark
factory, I started it as a public experiment more towards the start of the
year. Now, watching the factory itself run is very boring cuz we're just
waiting for agents to churn through work. But like I said, we're putting a lot
of that engineering effort into the harness up front. So, that is what I showed
with YouTube videos and live streams that I did. It was a blast and I built a
pretty successful dark factory. I covered this a lot back then, but my main
inspiration for building the dark factory was Dan Shapiro's blog post. He's
covering the five different levels of autonomy for AI coding here. Most of us,
we live our day-to-day like level three, maybe level four, but level five with
the dark software factory is the ultimate form of autonomy. And so, he uses the
analogy of driving a vehicle where with the dark factory, there's not even a
steering wheel. You supply the final destination or like what you want to
build, but nothing with the directions for how to actually get there. And that
sounds like the dream. Hey Claude, hey Codex, here's a massive app I want to
build. Go and create it. Don't stop until you're done. Make no mistakes. I
mean, that's kind of what it sounds like. And in theory, it seems like it would
be practical eventually because as LLMs get better and better and better, we
would reach this level of autonomy. Like it would actually become practical.
But there's a big problem with this. And this big problem relates to exactly
what I was covering in my last video. As LLMs get better and better, they
become better at building software, but not that much better at understanding
us and our intent. The bottleneck becomes getting what you actually want
because as humans, we're never going to perfectly communicate the features we
want to build, how we want to maintain our codebase, those kinds of things. And
so, I know it sounds kind of cheesy, but the dark factory is fundamentally
flawed because as powerful as LLMs get, they're never going to be able to just
read our minds. Now, I've also heard the argument, and I do find this
fascinating. People say that LLMs are going to get so good that their ideas and
their intent is going to become better than our own, and so we will fully hand
over the development of software. But, I just don't buy into that. I think we
will always need to be in the driver's seat because no matter how good LLMs
are, we're always going to understand what other people want. The problems
we're solving for, our customers, we're always going to know best. And to truly
keep us in the driver's seat, we also need to make sure that we're a part of
maintaining the code base. We can't take ourselves out of the code entirely
because also coding agents have a weird way of maintaining a code base. They
sprawl a lot, and this is actually the main argument of Dex Horthy. He gave a
really popular talk why software factories fail a couple of months ago, and his
main argument is code base maintainability. Agents just aren't able to keep it
up in the way that humans do, so we have to be a part of that process still. In
fact, Dex also did the same thing as me where he started with the dark factory
and had to dial it back a bit, adding more human in the loop to make it
actually realistic. Now, when he says software factories fail, I think that's
more in line with my definition of a dark factory, right? Like this is the
system that doesn't work. And so, I've taken all the lessons here that I've
explained. It's an important precursor, and that leads into the system I have
now that is genuinely working extremely well for me. And so, thinking about,
you know, how can we maintain human in the loop while still keeping the process
as autonomous as possible. How do we make it so we continue to help maintain
the code base? How do we keep the agents on track as they're ripping through
all these different tickets? All of this is built in. So, there's one big
difference here between the software factory and the dark factory, and I don't
want to get super caught up on definitions in general, but I think there is a
really important distinction here. So, I'll cover that with a more simplified
view of my software factory, then I'll get more into how each step works so you
can really see how reliability and human in the loop is built in. So, the big
difference between the AI software factory and Dark Factory, besides the
obvious human-in-the-loop that we'll talk about at the end, is the scope of
work that you build into the system and how much you plan that with the agent.
So, with the Dark Factory, we are as hands-off as we possibly can be. We create
just some kind of high-level document for this massive application we want to
create, and we expect the factory to split that into issues and handle them all
one at a time or some in parallel. The point is it is entirely lights out once
we give that more broad-level description of what we want to create. And we're
even letting the agent fill in the gap for some of our intent, right? And
that's the big problem I was talking about where we don't want the agent to
assume our intent, even if it is a very capable model. And so, what we're doing
with the software factory is we are giving individual releases into the system.
So, we're still having it rip through a ton of issues all by itself, but
instead of it just being like, "Build the entire thing, go." it's let's
actually figure out like, "What's the next scope of work?" Let's figure out the
tickets and how we want to split up the work. Then we let the factory handle it
autonomously. So, the core loop of the factory is still the same. How I handle
each individual GitHub issue, Jira ticket, whatever that might be. I have a
very similar way of building and validating, and it's always going to be the
issue is the input, the pull request is the output. That remains the same. It's
really a lot of what I do beforehand and after the fact that makes the factory
a lot more human-in-the-loop and reliable. And so, with that, let me go through
the three core parts of the factory here. Now, I'm going to stay pretty
high-level cuz I've spent hundreds of hours building this system and testing
it. Obviously, I could get really in the weeds, but I just want to generally
give you inspiration for the process, talk about what's really working in the
industry as a whole, and then let me know in the comments if you want me to
cover anything specific here in a dedicated video. Big thanks to Port for
backing today's video. They're the platform that helps teams run their own AI
software factory. Cuz here's the thing, everything I'm showing you in today's
video works for real engineering teams. I've built it myself. But when you
start to roll factories out to organizations where you have hundreds of
services, a bunch of teams, all these people and agents opening up pull
requests, you need something to help you manage all of it. Essentially, a
managed software factory. Your agents need to know who owns what and what
standards apply. And you need to actually be able to see what your agents are
shipping as they do so. And that is where Port comes in. They map your entire
environment into what they call the context lake. Here your services, owners,
docs, and standards all live in one catalog. You can also connect your agents
with Port's MCP server. Like right here in Cloud Code, I did so with a single
command. And so now my agent can query all my factories, get information like
who owns what, and get other context around the factory like its readiness and
which checks are failing. Cuz we're always going to have a standard to test
against for our factories. And because every pull request goes in Port's
catalog, I can ask my agent about a lot of context around my factories, like
how many pull requests each one is merging per month, things like how long my
laps are taking on average. These insights are very valuable if you want to
make improvements to your factories over time. And of course, I can set
permissions for my agent like this one here is just read-only. Port is free for
up to 15 seats, no credit card required, and it's free to try on your own
repos. I'll have a link to them in the description. So before we get into the
core loop of the factory, there's two steps. We need to plan the larger body of
work we want to accomplish in the next release, and then split it into tickets
so we have bite-size pieces of work that can each go through the full loop that
I'll cover in a second. Now, the first step here, the planning, I have
intentionally left out of the factory. Nothing in the harness is going to walk
you through this because I'm assuming you already have your own way of planning
with your agent. I have that myself, you probably do, every company I work
with. I don't really want to force that into the factory. And I want to be
fully in the loop with the planning. And so, you create your PRD, your
architecture document, whatever you usually do in your normal way, and then
that becomes input to the factory. So, we're planning our next release. Now,
the point of the software factory that makes it very different than the dark
factory is we're not going to try and just build the entire application. And
so, for greenfield, it's just simply a proof of concept. You want the factory
to build for that first release. And then for brownfield, because yes, the
factory works great if you apply it on top of existing codebases as well, it is
simply a small epic that you're going to define. Now, I know that small is very
much left up to interpretation for an epic. Every organization has a different
way that they scope work for an epic or release. It's really up to you. My
general rule of thumb is I want to create an epic document that's going to get
split into anywhere between 10 and 20 tickets. I know that's a large range.
Every ticket is going to be a very different size, but that's just the best
estimate I can give you. And so, if you build out your factory, you use this
system, you'll start to just build that muscle over time for, you know, that
size of epic that works well for you. But the point in the epic is you want to
describe both what we are building here and what specifically we are not
building. So, having things that are out of scope is also very helpful for the
factory just to continue to steer it as it's churning through the different
tickets. And then the other thing that we define up front that is more unique
to the factory, but is also just really helpful for any agentic coding
workflows, is defining the holdout scenarios. And so, essentially what a
holdout scenario is is it is a test that we're going to run at the end of the
implementation. But the implementer agent, the builder, doesn't actually know
what the holdout scenarios are, right? We're withholding that information. So,
that way there's no bias there. The agent can't overfit the implementation to
make our testing scenarios pass. This is a big thing that has boosted
reliability in my software factory because agents are sycophantic. If they know
the test scenarios you're going to be working with, they're going to try to
engineer the implementation just to get those to pass. And so, a lot of times
the software isn't really built well, it's just built well for those tests. And
so we don't want the builder to know what they are. So we define all of that in
a document. You create your usual PRD architecture doc, whatever, and then the
factory will take that and help you split it into tickets. And as a part of
this process, it's also going to help you do your dependency mapping. So
figuring out things that can be knocked out in parallel, dependencies that we
have, so we have to, you know, have a specific order for the laps that we
accomplish. The point is the factory is going to be applying GitHub labels to
set up all these dependencies to really set the core loop up for success, so
it's doing things and testing things in the right order. Now, we don't have to
have human in the loop here. A lot of what I'm building into my software
factory is sort of like toggles that we have for human in the loop, so maybe we
don't review PRs before we merge into staging or we do, or we do review the
split before we start building or we don't. And so every organization, every
person has different needs, right? And it also depends on the complexity of
what we're building in this specific release. So there might be some releases
where we're dealing with compliance and regulation, we really have to make sure
things are solid. So we want to review the split, we want to review the PRs at
the end, but we still want the system to just churn through the issues once we
do create them. And then there are other releases where we're maybe just
handling a big backlog of bugs. And in that case, maybe we just want to
entirely trust it to split into tickets and merge things right into our staging
environment, right? Like there's there's a sort of dynamic need that we have
where it's not always human in the loop needs to be this place, this place, and
so I've created the factory to be very adaptable. Now, trust me, I wish I could
really get into what this factory looks like in action, showing the runs,
showing my plans, the splits, and what the issue lists look like, but I did try
recording a version of this video where I showed all that, and it got way too
long. So I have to stay high-level for now, but definitely I will be getting
more into this in future videos. The point is here that after the planning and
the splitting, we have a list of GitHub issues, and we're just going to rip
through them with the core loop of the factory doing all the planning and
validation. So, zooming in here, we start with the GitHub issue. We can run
many of these labs in parallel because we did the dependency mapping, we know
things that we can knock out at the same time. So, each time we run a lap, it
is going to choose a single GitHub issue to work on. It'll apply a sort of
claim label, so other parallel labs don't pick it up, and then we make a
decision up front because something that I noticed with the first version of
even my dark factory is when I did the more comprehensive workflow to handle
every single implementation, there was these basic tickets that would take like
30 minutes or 20 minutes to implement where they really didn't need that. And
so, I make the decision up front actually using Jev, is this a simple thing
where I just have a faster build workflow, or is it more complex where we do
want to have the stages for iteration and things like that. And so, it makes
the decision, but either way, once it's done building, it's going to go through
the validation and code review that also understands, you know, based on the
complexity of the implementation, how much time do we have to spend here. And
so, there's both review and validation cuz they are different things.
Validation means as a part of the harness, I give it the tooling to actually
test the application as a user would. So, it replaces a lot of my manual
testing because we do want it to be more autonomous. That's the whole point of
the software factory. And so, clicking buttons, entering text in the chat
input, whatever it is for the application. And then after we do the code
review, and this is more analyzing like since we know that the app is working,
now let's make sure that it's simple, the code is maintainable, it was
implemented correctly, right? Like those kinds of more software engineering
decisions, the the more classic code review. And then for anything that it
deems incorrect in either one of these stages, it sends back to the
implementation workflow to fix, right? So, even for a complex implementation,
it's just going to go through the simple workflow to address any feedback. And
of course, there are max retries, so we don't get stuck in an infinite loop
with the factory. And so, then once we are done with our reviewing and
potential iterating, then we allow to merge the pull request into whatever
branch goes into our staging environment only if CI is green and the reviewed
code is good. And then for this entire process here, I have a manager agent
that runs on a periodic basis like every two or three hours and it's kind of
surveying the success of all the laps together because this is actually the
most recent thing I've added into the factory. Before I had this, these agents
are never really communicating, right? Like each individual lap isn't really
understanding if dependencies are changing or if one pull request is getting
really stuck. Like if we hit the max retries and an agent really is getting
stuck on a problem, we need something that kind of peers over the entire
process and can realign issues or kind of like hijack a workflow and finish it
if needed. And this has also really increased the reliability because also I've
set it up where it will actually alert me if I really do need to come into the
system. Because as much as we want this to be autonomous, it's not a dark
factory anymore. We are okay with once in a while us having to come in and
review the split or, you know, sort of rescue a workflow. It happens once in a
while. So usually I'll just have my main Claude code agent like my second brain
help me when the manager is alerting me of these issues. And then of course the
holdout scenarios come in because we're running those for the app validation.
And as a part of the factory, I have my core context. I call it my mission.md
or engineering.md. It's the things that are out of scope that I never want to
build and just higher level direction for how I want the agent to operate in my
code base. So kind of that plus the global rules together. And I'm making sure
that I never edit these files. That's a part of my review making sure that we
never touch those because I don't want the factory to be able to change its own
permissions and behavior. And then the last thing right here is for every
single one of these nodes, I'm using different models and even different
providers because this factory I've made it very token efficient. We don't
always need the most reasoning possible. So definitely for a lot of the
planning that I'm doing like right here, I am using you know Opus 5.5 or GPT-6
Astra. But for a lot of these individual nodes, like using Jev to pick the task
and then for simple maybe just using Sonnet 5.5. I mean even for shipping these
different nodes in here, I don't have to use the best model. And so I've done a
lot of that experimentation optimizing for the sake of tokens. I'm running
hundreds and hundreds of laps every single week not hitting my rate limits. All
right, and then the last part of the process here, this is where we come back
in to review things. And so we build up all the issues for the epic within our
core loop. We merge things into the staging environment. This is where we get
to validate things ourselves cuz we need the step to verify our intent. And so
we test things ourselves and then anything that's off like if something wasn't
built how we actually wanted it to be, all we have to do is simply create a new
issue in the repository and the factory will pick that up automatically just
like it did with the initial split from our epic document. And so it's very
easy for us to sort of test the batch of features in the epic and then give
batch feedback. We we could you know create four or five issues, whatever, and
then it'll just rip through all of these and then we can test staging again.
And then we go to the production once it's right. And so the dark factory
pretty much goes straight to production, but the software factory, I found this
to be very important. So we have true human in the loop, but at the same time
we get to review a lot at once. And so we are solving that bottleneck at least
partially for the human review at the end. And then once we're happy with
what's in production, we can simply just go on to the next release and repeat
this process going through the planning, core loop, and the staging and
production. And that's it. That is the AI software factory at a high level. And
so of course, like I already said, let me know if you want me to cover any part
of this in more detail, but hopefully you found this inspirational just take
aways for your own AI coding workflows or if you want to build a software
factory yourself, it really is the future of agentic engineering. And so if you
appreciate this video, you're looking forward to more things on an AI software
factory and AI coding in general, I would really appreciate a like and a
subscribe. And with that, I will see you in the next video.
