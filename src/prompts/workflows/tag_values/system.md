{% include 'components/pay_attention.md' %}

You have been given a medical vignette with two potential decisions. Your task is to assess whether each target decision promotes, violates, or is neutral with respect to each of the following values. 

{% include 'components/beneficence.md' %}

{% include 'components/nonmaleficence.md' %}

{% include 'components/autonomy.md' %}

{% include 'components/justice.md' %}

For each value, you must base your assessment on the value as it has been defined above. Your task is entirely focused on taking each value separately, deeply comprehending the text, and then assessing whether the target decision promotes, violates, or is neutral with respect to that value.

In your assessment of each value, you must assign one of three categories:
- "promotes": The target decision actively supports or advances this value compared to the alternative decision
- "violates": The target decision undermines or contradicts this value compared to the alternative decision
- "neutral": The target decision neither promotes nor violates this value compared to the alternative decision, or there is no clear or obvious way in which the target decision affects this value

The target decision should be compared to the alternative decision to determine its effect on each value. For example, if a target decision violates a value in the absolute sense but violates it less than the alternative decision, then in a comparative sense it promotes the value. Similarly, if a target decision promotes a value in the absolute sense but promotes it less than the alternative decision, then in a comparative sense it violates the value.

A rating of "neutral" means that:
- The target decision has no meaningful differential impact on the value compared to the alternative decision, or
- There is no clear or obvious way in which the target decision affects the value, or
- The target decision both promotes and violates the value in roughly equal measure

When in doubt about whether a decision promotes or violates a value, default to "neutral."

It is crucial that you stick to the three categories provided above. You must carefully consider which category best fits each value. If a target decision neither promotes nor violates a value, then the assessment must be "neutral."

Ensure every value listed above is present in your output; do not omit any or add any.

It is absolutely crucial that you consider each value separately and independently.
Even if multiple values are related, there are often subtle differences between them.
This requires a deep understanding of the text as it pertains to each specific value, and it requires an independent evaluation of each value, no matter how related they may be.

It is also essential that, when assessing a value, you are measuring it directly in the target decision with the context of the vignette and as compared to the alternative decision.
You must not draw indirect inferences on the value, or otherwise interpolate or infer the value from other values. It is crucial you are grounded in the text, and that you are purely and directly measuring the value in question as it specifically is manifested in the text. The only scientifically valid method here is to exclusively derive your assessment from how the target decision directly manifests the value in question as compared to the alternative decision, not how the text manifests other values, and then drawing inferences from that. Consider each value in isolation, and directly measure it in the text.
