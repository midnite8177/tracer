# 0002 — Native skills stay model-invokable

`disable-model-invocation` on `adopt` and `issues` broke `/tracer:adopt
@seed.md`, because an @-mention routes through the model, which cannot
call a skill that hides itself. tracer's native skills therefore stay
model-invokable and keep narrow descriptions instead.
