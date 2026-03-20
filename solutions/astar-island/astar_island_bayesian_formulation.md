# Astar Island as a Bayesian Inference and Decision Problem

## Purpose

This note formalises the **Astar Island** challenge as a Bayesian inference problem with a sequential decision layer for query selection.

It is written to be:

- repository friendly
- LLM friendly
- mathematically explicit
- easy to convert later into other formats if needed

The emphasis is on the **shared hidden round-level parameters across the 5 seeds**, because that is the main source of transferable signal.

---

## 1. Problem setup

In each round, we must submit, for each of 5 seeds, a tensor of shape:

$$
40 \times 40 \times 6
$$

where the last dimension is a probability distribution over the six final terrain classes after 50 years of stochastic simulation:

- \(0\) = Empty / Ocean / Plains
- \(1\) = Settlement
- \(2\) = Port
- \(3\) = Ruin
- \(4\) = Forest
- \(5\) = Mountain

For each seed:

- the initial map is known exactly
- the simulator is stochastic
- hidden world parameters are shared across all 5 seeds in the round
- we have a budget of 50 queries
- each query returns a \(15 \times 15\) viewport from **one sampled rollout**
- repeated queries to the same viewport yield independent stochastic samples, not probabilities directly

The challenge score is based on **entropy-weighted KL divergence** between the submitted distribution \(q\) and the true Monte Carlo distribution \(p\).

---

## 2. Formal Bayesian model

### 2.1 Indices

Let:

- \(s \in \{1,\dots,5\}\) index seeds
- \(u \in \mathcal{G}\) index grid cells, with \(|\mathcal{G}| = 40 \times 40 = 1600\)
- \(k \in \{0,1,2,3,4,5\}\) index classes
- \(t \in \{1,\dots,T\}\), with \(T \le 50\), index queries

---

### 2.2 Known initial conditions

Let the known initial condition for seed \(s\) be:

$$
x_s \in \mathcal{X}
$$

where \(x_s\) includes:

- the full initial terrain
- visible starting settlements
- any other visible initial state features

These are observed exactly before any query is made.

---

### 2.3 Hidden round-level parameters

Let the hidden round-level state be:

$$
\Theta \in \ThetaSpace
$$

This is the latent variable controlling the world dynamics of the round, such as:

- expansion rate
- aggression
- winter severity
- trade effects
- collapse tendency
- destruction intensity
- growth limitations

A useful decomposition is:

$$
\Theta = (R, \theta)
$$

where:

- \(R\) is a discrete **round regime**
- \(\theta\) is a continuous or structured parameter vector within that regime

For example:

$$
R \in \{\text{collapse},\ \text{static},\ \text{moderate},\ \text{high-dynamic}\}
$$

This discrete regime variable is useful because some rounds appear to undergo abrupt regime shifts rather than smooth parameter variation.

---

### 2.4 Seed-specific stochastic final worlds

For each seed \(s\), a full simulator rollout after 50 years is a random final world:

$$
W_s^{(m)} \sim P_{\Theta}(\cdot \mid x_s)
$$

where \(m\) indexes independent simulator rollouts under the same hidden round-level state \(\Theta\).

Let:

$$
Y_s^{(m)} = g(W_s^{(m)})
$$

be the final class map extracted from the full world state, so that:

$$
Y_{s,u}^{(m)} \in \{0,1,2,3,4,5\}
$$

for each cell \(u\).

---

### 2.5 Unknown per-cell final distributions

For fixed \(\Theta\), the true class distribution at cell \(u\) in seed \(s\) is:

$$
p_{s,u,k}(\Theta)
=
\Pr(Y_{s,u}^{(m)} = k \mid x_s, \Theta)
$$

and the full class vector is:

$$
p_{s,u}(\Theta)
=
\bigl(p_{s,u,0}(\Theta),\dots,p_{s,u,5}(\Theta)\bigr)
\in \Delta^6
$$

where \(\Delta^6\) is the 6-class probability simplex.

This is the evaluator's target distribution for that cell.

From our perspective, before inference, the object of uncertainty is the random simplex-valued quantity:

$$
P_{s,u} = p_{s,u}(\Theta)
$$

because \(\Theta\) is unknown.

---

## 3. Prior, likelihood, posterior, predictive

### 3.1 Prior over hidden round parameters

A natural hierarchical prior is:

$$
\pi_0(R,\theta) = \pi_0(R)\,\pi_0(\theta \mid R)
$$

Given \((R,\theta)\), the seed-specific rollouts are:

$$
W_s^{(m)} \mid x_s, R,\theta
\overset{\text{iid in } m}{\sim}
P_{R,\theta}(\cdot \mid x_s)
$$

for \(s = 1,\dots,5\).

This induces a prior over each cell distribution \(P_{s,u}\) through the simulator.

---

### 3.2 Query observation as a probabilistic object

A query chooses:

- a seed \(s_t\)
- a viewport \(V_t \subset \mathcal{G}\) of size \(15 \times 15\)

The query returns visible information from one sampled rollout for that seed and viewport.

Let \(h_{V_t}\) be the observation operator that extracts the visible information from the final world in that viewport. Then:

$$
O_t = h_{V_t}\bigl(W_{s_t}^{(m_t)}\bigr)
$$

where \(m_t\) is a fresh rollout index.

This is crucial:

**A query is not an observation of probabilities. It is a partial observation from one stochastic rollout.**

---

### 3.3 Exact likelihood of one query

For a chosen action \(a_t = (s_t, V_t)\), the exact likelihood is:

$$
L_t(R,\theta)
=
\Pr(O_t = o_t \mid x_{s_t}, a_t, R,\theta)
$$

Equivalently:

$$
L_t(R,\theta)
=
\int
\mathbf{1}\{h_{V_t}(w) = o_t\}
\,P_{R,\theta}(dw \mid x_{s_t})
$$

This is the correct patch-level likelihood induced by the simulator.

It does **not** assume independence between cells within a viewport.

---

### 3.4 Full likelihood after \(T\) queries

If each query uses an independent rollout:

$$
\Pr(D_T \mid R,\theta, x_{1:5})
=
\prod_{t=1}^{T}
L_t(R,\theta)
$$

where the observed data are:

$$
D_T = \{(s_t, V_t, o_t)\}_{t=1}^{T}
$$

---

### 3.5 Posterior after observing queries

The posterior is:

$$
\pi(R,\theta \mid D_T, x_{1:5})
\propto
\pi_0(R,\theta)\,
\prod_{t=1}^{T} L_t(R,\theta)
$$

This induces a posterior over all cell-level class distributions \(P_{s,u}\).

---

### 3.6 Predictive distribution for submission

The standard posterior predictive probability for class \(k\) at seed \(s\), cell \(u\), is:

$$
\bar{p}_{s,u,k}
=
\Pr(Y_{s,u}^{\text{new}} = k \mid D_T, x_s)
=
\mathbb{E}\bigl[p_{s,u,k}(R,\theta) \mid D_T\bigr]
$$

This is the posterior mean of the true cell distribution.

Whether this is exactly the optimal submission depends on the scoring rule.

---

## 4. What kind of model is this?

This problem is simultaneously:

### 4.1 A hierarchical Bayesian model

Because:

- each seed has known seed-specific initial conditions \(x_s\)
- all seeds share the same hidden round-level latent state \(\Theta\)

So the seeds are conditionally independent given \(\Theta\), but marginally dependent.

---

### 4.2 A latent-variable model

Because the core unknown is the hidden round-level simulator state \(\Theta\), which is not directly observed.

---

### 4.3 A sequential experimental design problem

Because queries are chosen adaptively under a fixed budget, and each query changes the posterior and therefore changes the optimal final submission.

---

### 4.4 Clean summary

Structurally, this is a **hierarchical latent-variable Bayesian model**.

Operationally, it is a **Bayesian sequential experimental design problem**.

---

## 5. Decision-theoretic objective

Suppose the score for one cell is proportional to:

$$
-\,w(p)\,\mathrm{KL}(p \| q)
$$

where:

- \(p \in \Delta^6\) is the true class distribution for that cell
- \(q \in \Delta^6\) is the submitted distribution
- \(w(p)\) is an entropy-based weight

Then the Bayes decision problem is to choose \(q\) to maximise posterior expected utility, equivalently to minimise posterior expected loss:

$$
q^*
=
\arg\min_{q \in \Delta^6}
\mathbb{E}\bigl[
w(P)\,\mathrm{KL}(P \| q)
\mid D_T
\bigr]
$$

---

### 5.1 Expand the KL term

Recall:

$$
\mathrm{KL}(P \| q)
=
\sum_{k=0}^{5}
P_k \log \frac{P_k}{q_k}
$$

So the posterior expected loss is:

$$
\mathcal{L}(q)
=
\mathbb{E}\left[
w(P)\sum_{k} P_k \log P_k
\mid D_T
\right]
-
\sum_k
\mathbb{E}\left[w(P)P_k \mid D_T\right]\log q_k
$$

The first term does not depend on \(q\), so minimising \(\mathcal{L}(q)\) is equivalent to maximising:

$$
\sum_k \alpha_k \log q_k
\quad\text{where}\quad
\alpha_k = \mathbb{E}\bigl[w(P)P_k \mid D_T\bigr]
$$

subject to:

$$
\sum_k q_k = 1
$$

The solution is:

$$
q_k^*
=
\frac{\alpha_k}{\sum_j \alpha_j}
=
\frac{\mathbb{E}[w(P)P_k \mid D_T]}
{\mathbb{E}[w(P) \mid D_T]}
$$

---

### 5.2 Implication

If \(w(p)\) is constant across cells, then:

$$
q_k^* = \mathbb{E}[P_k \mid D_T]
$$

So the optimal submission is the **posterior mean**.

If \(w(p)\) depends on the true entropy of \(p\), then the optimal submission is generally the **entropy-weighted posterior mean**, not the ordinary posterior mean.

This is the correct Bayes action under entropy-weighted KL.

---

## 6. Practical approximations

Exact inference is unlikely to be tractable. The following approximations are principled and operationally useful.

---

### 6.1 Regime mixture model

Introduce a discrete regime variable:

$$
R \in \{\text{collapse},\ \text{static},\ \text{moderate},\ \text{high-dynamic}\}
$$

and perform inference on:

$$
\Pr(R,\theta \mid D)
\propto
\Pr(R)\Pr(\theta \mid R)\Pr(D \mid R,\theta)
$$

This helps capture abrupt regime shifts, especially collapse-like rounds.

This is likely the most important modelling feature.

---

### 6.2 Dirichlet-multinomial estimation

A tractable approximation is to model class probabilities in a feature bucket \(b\) as:

$$
p_b \sim \mathrm{Dirichlet}(\alpha_b)
$$

After observing counts \(n_{b,k}\), the posterior is:

$$
p_b \mid D
\sim
\mathrm{Dirichlet}(\alpha_{b,0}+n_{b,0},\dots,\alpha_{b,5}+n_{b,5})
$$

with posterior mean:

$$
\mathbb{E}[p_{b,k}\mid D]
=
\frac{\alpha_{b,k}+n_{b,k}}
{\sum_j \alpha_{b,j} + n_b}
$$

where:

$$
n_b = \sum_k n_{b,k}
$$

This is more useful if \(b\) is not a single cell, but a feature-defined group such as:

- initial terrain type
- coastal adjacency
- distance to initial settlement
- local neighbourhood structure
- known dynamic susceptibility

---

### 6.3 Separate dynamic mass from class composition

Define the dynamic class set:

$$
\mathcal{D} = \{1,2,3\}
$$

and the dynamic mass:

$$
\rho_{s,u}(\Theta)
=
\Pr(Y_{s,u} \in \mathcal{D} \mid x_s, \Theta)
$$

Then decompose the prediction into:

1. probability of dynamic vs static
2. conditional split within dynamic classes
3. conditional split within static classes

This is useful because the biggest failure mode often comes from getting the **total dynamic mass** wrong, not just the relative proportions among settlement, port, and ruin.

A Beta prior can be used for dynamic mass:

$$
\rho_{s,u} \mid R,\phi_{s,u}
\sim
\mathrm{Beta}(a_R(\phi_{s,u}), b_R(\phi_{s,u}))
$$

where \(\phi_{s,u}\) are cell-level features.

---

### 6.4 Empirical Bayes across the 5 seeds

Because the 5 seeds share the same hidden round state, pooled evidence from all seeds should be used to estimate round-level hyperparameters.

Within a round:

$$
\pi(\Theta \mid D_{1:5})
\propto
\pi_0(\Theta)
\prod_{s=1}^{5}
\Pr(D_s \mid x_s, \Theta)
$$

This is effectively empirical Bayes or pooled Bayes across the 5 seeds.

---

### 6.5 Shrinkage toward a static-world prior

Let \(p^{\text{static}}_{s,u}\) be a static baseline based on initial terrain and strong persistence assumptions.

Let \(p^{\text{dynamic}}_{s,u}\) be a more flexible dynamic model.

Then use:

$$
q_{s,u}
=
(1-\lambda_{s,u})\,p^{\text{static}}_{s,u}
+
\lambda_{s,u}\,p^{\text{dynamic}}_{s,u}
$$

where \(\lambda_{s,u}\) depends on:

- posterior probability of a dynamic regime
- local features
- observed evidence of actual activity

In collapse rounds, \(\lambda_{s,u}\) should shrink quickly toward zero.

---

### 6.6 Regime detection as Bayesian model comparison

A mathematically clean way to detect collapse is:

$$
\Pr(R=r \mid D)
\propto
\Pr(R=r)\Pr(D \mid R=r)
$$

This is direct posterior model comparison between competing round-level regimes.

---

## 7. Why the shared round-level parameters matter

This is the key structure of the problem.

Because the hidden parameters are shared across all 5 seeds, observations from one seed update beliefs for all other seeds.

Formally:

$$
\pi(\Theta \mid D_{1:5})
\propto
\pi_0(\Theta)
\prod_{s=1}^{5}
\Pr(D_s \mid x_s, \Theta)
$$

Then for any seed \(s'\) and cell \(u\):

$$
\Pr(Y_{s',u}=k \mid D_{1:5}, x_{s'})
=
\int
p_{s',u,k}(\Theta)\,
\pi(d\Theta \mid D_{1:5})
$$

So if evidence from seed 1 strongly favours a collapse regime, then the predicted dynamic mass in seeds 2, 3, 4, and 5 should also drop, even with limited direct observation there.

This is why modelling seeds independently wastes signal.

---

## 8. Query strategy as a Bayesian design problem

At query time \(t\), let the current observed data be \(D_t\).

Define the Bayes risk as:

$$
\mathcal{R}(D_t)
=
\sum_{s,u}
\min_{q_{s,u}\in\Delta^6}
\mathbb{E}\bigl[
w(P_{s,u})\mathrm{KL}(P_{s,u}\|q_{s,u})
\mid D_t
\bigr]
$$

For a candidate next query \(a\), define the one-step value of information:

$$
\mathrm{VoI}(a \mid D_t)
=
\mathcal{R}(D_t)
-
\mathbb{E}_{O \sim \Pr(\cdot \mid D_t, a)}
\left[
\mathcal{R}(D_t \cup \{(a,O)\})
\right]
$$

The ideal next query is:

$$
a_t^*
=
\arg\max_a
\mathrm{VoI}(a \mid D_t)
$$

Exact optimisation is hard, but this is the right decision-theoretic framing.

---

### 8.1 Tiling versus repetition

#### Tile broadly when:

- the round regime is already known fairly well
- the remaining uncertainty is mainly spatial
- the world appears mostly deterministic or static
- you need coverage more than repeated probability estimation

#### Repeat a viewport when:

- regime uncertainty is still large
- the viewport is strategically informative
- you need to distinguish collapse vs dynamic worlds
- high-entropy local outcomes matter
- early evidence can shift beliefs globally across all 5 seeds

---

### 8.2 Operational budget logic

A principled allocation is:

#### Phase 1: regime detection
Use the early queries on highly informative sentinel regions:

- around initial settlements
- coastal regions
- plausible growth frontiers
- regions where dynamic classes should appear if the round is active

Repeat some of these viewports to estimate whether the world is truly dynamic.

#### Phase 2: representative coverage
Once the posterior over regime is more concentrated, spend more queries covering diverse terrain and seed types.

#### Phase 3: targeted refinement
Use remaining queries on:

- high-posterior-entropy regions
- cells most sensitive to regime uncertainty
- seeds whose initial conditions interact most strongly with the inferred round state

---

## 9. Collapse/static round detection

In a bad round, almost all dynamic classes disappeared and the world collapsed mostly into class 0 and class 4.

This should be handled through posterior regime collapse.

---

### 9.1 Dynamic mass view

Again define:

$$
\mathcal{D} = \{1,2,3\}
$$

and:

$$
\rho_{s,u}(\Theta)
=
\Pr(Y_{s,u} \in \mathcal{D} \mid x_s,\Theta)
$$

Now compare two regimes:

- \(R = C\): collapse regime with very low dynamic mass
- \(R = D\): dynamic regime with much higher dynamic mass

Suppose we repeatedly query sentinel patches where dynamic activity should appear if the world is dynamic.

If we repeatedly observe no dynamic classes, then the Bayes factor in favour of collapse increases rapidly.

Using a crude Bernoulli approximation for dynamic vs non-dynamic observations:

$$
\mathrm{BF}_{C:D}
\approx
\prod_{i=1}^{n}
\frac{1-\rho_C^{(i)}}{1-\rho_D^{(i)}}
$$

If:

$$
\rho_C \approx 0.02
\quad\text{and}\quad
\rho_D \approx 0.20
$$

then each non-dynamic effective observation contributes roughly a multiplicative factor of:

$$
\frac{0.98}{0.80} \approx 1.225
$$

in favour of collapse.

With repeated evidence across informative patches, the posterior can move decisively toward collapse.

---

### 9.2 What the posterior should do

Once posterior mass shifts toward collapse or static regimes, predictions should respond sharply:

- reduce total mass on classes \(1,2,3\)
- revert strongly toward static terrain persistence
- reserve dynamic mass only where there is overwhelming local evidence

The correct Bayesian behaviour is not to make a mild adjustment. It is to **collapse posterior mass toward near-static predictions**.

---

## 10. Concise model summary

The cleanest minimal formalisation is:

### Generative model

$$
(R,\theta) \sim \pi_0(R,\theta)
$$

$$
W_s^{(m)} \mid x_s, R,\theta
\overset{\text{iid}}{\sim}
P_{R,\theta}(\cdot \mid x_s)
$$

$$
p_{s,u,k}(R,\theta)
=
\Pr(Y_{s,u}^{(m)} = k \mid x_s, R,\theta)
$$

$$
O_t = h_{V_t}(W_{s_t}^{(m_t)})
$$

---

### Likelihood

$$
\Pr(D_T \mid R,\theta)
=
\prod_{t=1}^{T}
\Pr(O_t = o_t \mid x_{s_t}, V_t, R,\theta)
$$

---

### Posterior

$$
\pi(R,\theta \mid D_T)
\propto
\pi_0(R,\theta)\Pr(D_T \mid R,\theta)
$$

---

### Predictive distribution

$$
\bar{p}_{s,u,k}
=
\mathbb{E}[p_{s,u,k}(R,\theta)\mid D_T]
$$

---

### Bayes-optimal submission under entropy-weighted KL

$$
q_{s,u,k}^*
=
\frac{\mathbb{E}[w(P_{s,u})P_{s,u,k}\mid D_T]}
{\mathbb{E}[w(P_{s,u})\mid D_T]}
$$

If \(w\) is constant, this reduces to:

$$
q_{s,u,k}^*
=
\mathbb{E}[P_{s,u,k}\mid D_T]
$$

---

## 11. Concrete modelling recommendations

1. **Model the round with an explicit discrete regime variable**
   - include at least a collapse/static regime versus a dynamic regime

2. **Pool evidence across all 5 seeds immediately**
   - the seeds are coupled through the same hidden round parameters

3. **Separate total dynamic mass from within-dynamic class composition**
   - first estimate whether a cell is dynamic at all
   - then estimate settlement / port / ruin composition if dynamic

4. **Use strong shrinkage toward a static baseline**
   - only move away from static predictions when the posterior supports it

5. **Spend early queries on regime detection**
   - repeated sentinel viewports are often more valuable than naive full coverage

6. **Treat collapse detection as Bayesian model comparison**
   - do not smooth it away as a weak perturbation

7. **Submit the entropy-weighted posterior mean if the score is truly entropy-weighted in the true \(p\)**
   - otherwise use the ordinary posterior predictive mean

---

## 12. Best storage format for repo and LLM use

For your repo and downstream LLM use, the best default format is:

- **UTF-8 Markdown (`.md`)**
- plain headings
- short paragraphs
- LaTeX maths in `$$ ... $$` display blocks and `\( ... \)` or `$...$` inline
- minimal tables
- minimal Word-specific formatting

Why this is usually best:

- easy to diff in Git
- easy for LLMs to ingest
- easy to convert later to PDF, HTML, or DOCX
- preserves equations more reliably than rich text copy-paste

If you later need a Word version, the cleanest pipeline is usually:

- write in Markdown first
- convert to `.docx` or `.pdf` afterwards with a converter

For repo storage and future run iteration notes, `.md` is the right primary format.

---

## 13. Short practical takeaway

The core inferential problem is not just local cell prediction.

It is:

1. infer the hidden round-level world regime
2. use all 5 seeds to update that regime posterior
3. shrink local predictions according to the inferred regime
4. spend query budget where it most reduces posterior decision risk

The biggest modelling error is to treat each seed independently or to keep assigning dynamic mass after the posterior should already have collapsed toward a static world.
