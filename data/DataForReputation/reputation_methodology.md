# Research Methodology: Short-Term Corporate Reputation Prediction

### PhD Research Draft | Data Science

\---

## Research Question

*What is the relationship between real-time online signals (sentiment changes, engagement level, discussion volume, and related indicators) and short-term corporate reputation changes (6–24 hours), as reflected in sentiment shifts and observable stakeholder behavior (stock price movements)?*

\---

## Methodological Overview

This study adopts a **multi-stage, sequential mixed-methods computational pipeline** combining retrospective ML model training with prospective real-time inference. The overall design follows the structure: **Data Acquisition → Preprocessing \& Signal Construction → Sentiment Analysis → Event Detection → Causal \& Correlation Analysis → Prediction \& Evaluation**. Each stage is described below with methodological justification and academic grounding.

\---

## Stage 1: Data Acquisition

### 1.1 Historical Data Collection (Retrospective Phase)

The retrospective dataset serves as the training corpus for all ML components. Collection targets a minimum **3-year window** to capture diverse market regimes and reputation event types.

**Data sources:**

* **Social media**: Twitter/X, Reddit (r/wallstreetbets, r/investing, company-specific subreddits), StockTwits via official APIs and academic API tiers
* **News \& financial press**: Reuters, Bloomberg, Financial Times, Yahoo Finance via web scraping (BeautifulSoup / Scrapy) and financial data APIs (Alpha Vantage, NewsAPI, GDELT)
* **Stock market data**: OHLCV (Open, High, Low, Close, Volume) data from Yahoo Finance or Polygon.io, including Abnormal Returns computed relative to market benchmark (S\&P 500)
* **Engagement metrics**: retweet/reply counts, upvotes, comment velocity, share counts — treated as proxy signals for stakeholder behavior

> \*Khalil (2026) uses a comparable multisource dataset spanning 2019–2024 that integrates Yahoo Finance stock data with Reddit, Twitter, Bloomberg, and Reuters sentiment signals for financial market prediction (Journal of Modelling in Management).\*

> \*For temporal alignment, monthly averages are appropriate for macro-level studies, but this research targets 6–24 hour windows requiring hourly or sub-hourly data granularity — a critical distinction from most existing literature.\*

### 1.2 Real-Time Data Collection (Prospective Phase)

Once models are trained and validated retrospectively, a **streaming pipeline** is deployed:

* **Streaming APIs**: Twitter Filtered Stream API, Reddit PRAW live feeds, RSS feed monitoring for major news outlets
* **Scraping cadence**: Rolling web scraping at 15-minute intervals for news sources not accessible via API
* **Storage**: Time-stamped document store (MongoDB or Elasticsearch) with company-entity tags applied at ingestion

**Scope definition**: Select 5–10 publicly traded companies across 2–3 sectors to control for industry-level confounding. Ensure each company has had at least one documented reputation event (product recall, executive scandal, regulatory action) in the historical window.

\---

## Stage 2: Text Preprocessing Pipeline

Preprocessing is not trivial for reputation monitoring. Noisy social media text — bots, sarcasm, abbreviations, platform-specific conventions — directly undermines sentiment model reliability. The pipeline below is sequenced deliberately.

### 2.1 Bot Filtering (Critical Pre-Step)

Bot-generated content must be excluded **before** any sentiment scoring, not after. Including bot traffic inflates volume metrics and can manufacture false sentiment signals — a confound that invalidates downstream causal analysis.

**Recommended approach**: A behavioral + textual bot detection classifier using an ensemble of Logistic Regression, Random Forest, and XGBoost on features including posting frequency, account age, follower/following ratio, textual repetition scores, and hashtag farming patterns. Ensemble classifiers on these feature sets reach \~95% accuracy with high computational efficiency for real-time deployment.

> \*A CNN-BiLSTM/GRU hybrid bot detection architecture (IEEE Access, DOI: 10.1109/ACCESS.2024.3430859) achieves strong performance on the Twibot-20 benchmark and represents the deep learning upper bound, though the ensemble approach is preferred for real-time throughput.\*

> \*Cross-feature integration of profile features, text analysis, and graph-based techniques (TMTM framework, 2024) improves detection accuracy by \~5.5% over single-modality approaches.\*

### 2.2 Noise Removal

* Remove URLs, hyperlinks, HTML tags
* Strip @mentions and #hashtags (retain hashtag *text* as a separate feature for topic tracking)
* Remove special characters, non-UTF8 sequences
* Filter duplicate and near-duplicate posts (cosine similarity threshold ≥ 0.92 on TF-IDF vectors)

### 2.3 Normalization

* **Lowercasing** (applied after emoji conversion to avoid case-dependent emoji misclassification)
* **Emoji conversion**: Map emojis to sentiment-tagged text tokens using the `emoji` Python library and a curated financial/corporate reputation lexicon supplement. Emojis carry significant sentiment signal in social media and must not be discarded.
* **Abbreviation expansion**: Expand financial abbreviations (e.g., "EPS miss", "CEO quits") using a custom financial abbreviation dictionary. Standard NLP abbreviation expanders (e.g., contractions library) are insufficient for this domain.
* **Tokenization**: Use a subword tokenizer consistent with downstream transformer models — specifically WordPiece (BERT/DistilBERT) or BPE (RoBERTa). Do **not** apply standard NLTK word tokenization before transformer models, as this pre-tokenizes text in ways that conflict with subword tokenization schemes.

### 2.4 Signal Feature Engineering

Beyond cleaned text, construct time-series signals:

|Feature|Definition|Window|
|-|-|-|
|Discussion Volume (DV)|Post count per entity per hour|Rolling 1h|
|Sentiment Velocity (SV)|Rate of change of mean sentiment score|1h delta|
|Engagement Rate (ER)|(Likes + Shares + Comments) / Impressions|Rolling 1h|
|Negative Spike Index (NSI)|Z-score of negative post volume vs. 7-day baseline|Per event|
|Source Diversity Score|Shannon entropy of source origins|Rolling 6h|

\---

## Stage 3: Sentiment Analysis — Model Selection \& Comparison

Rather than committing to a single model, this study employs a **comparative framework** to identify the best-performing approach across reputation-specific evaluation criteria (nuance, domain alignment, inference speed). This is itself a contribution — the literature lacks a rigorous model comparison anchored specifically to corporate reputation text.

### 3.1 Rule-Based Baseline

**VADER** (*Hutto \& Gilbert, 2014*): Fast, interpretable, no training required. Well-calibrated for short social media text. Used as the **baseline** against which all learned models are benchmarked. Known weakness: handles negation and domain-specific financial language poorly.

### 3.2 Deep Learning Models

**BERT** (Devlin et al., 2019): Bidirectional contextual encoding. Strong general-purpose baseline for fine-tuned sentiment tasks. Serves as the reference transformer.

**RoBERTa** (Liu et al., 2019): Robustly optimized BERT variant with dynamic masking and no next-sentence prediction objective. Consistently outperforms BERT on sentiment tasks with sufficient training data.

**DistilBERT**: Compressed BERT (66% parameters, \~60% faster inference) with \~97% of BERT's performance. Preferred for the **real-time inference** phase where latency is a constraint.

**FinBERT** (Yang et al., 2020): Pre-trained on financial corpora (Reuters, earnings call transcripts). Critically, FinBERT achieves **F1 = 0.87–0.89 on Financial PhraseBank**, outperforming both zero-shot GPT-4o and RoBERTa by 3–6 F1 points in financial domain tasks.

> \*A 2025 study proposes \*\*FinRoBERT-FSA\*\*, combining FinBERT's domain-specific pretraining with RoBERTa's deep contextual understanding as a fine-grained hybrid — directly applicable to this research design (Zaâbi \& Boukhris, LNBIP Vol. 560, Springer, 2025).\*

> \*NAACL 2024 benchmark (Zhang et al., 2024) cautions that general LLMs underperform domain-fine-tuned SLMs on complex sentiment tasks including sarcasm and aspect-level opinion extraction — reinforcing the case for domain-specific fine-tuning over zero-shot LLM deployment.\*

**LSTM** (Hochreiter \& Schmidhuber, 1997): Included as a sequential baseline to model temporal dependencies within a text sequence and as a temporal model for sentiment time-series (post-scoring). Also tested in a **stacked LSTM with sliding window** configuration for short-term price movement prediction.

> \*Stacked LSTM with sliding window outperforms baseline LSTM, GRU, and classical ML in RMSE, MAE, and MAPE for short-term financial prediction tasks (Frontiers in AI Applications, 2025).\*

### 3.3 Evaluation Criteria for Model Selection

Models are compared on:

* **F1-score** (macro) on held-out labeled reputation corpus
* **Aspect-level accuracy** (sarcasm, irony, domain jargon)
* **Inference latency** (ms/document) — critical for 6h window constraint
* **Correlation with stock Abnormal Returns** (external validity check)

The winning model, or an **ensemble via weighted soft voting**, is carried forward to Stage 4.

\---

## Stage 4: Event Detection

### 4.1 Why Not Reinforcement Learning Here

The draft methodology proposes RL for event detection. This should be reconsidered: **RL is poorly suited for retrospective event identification** because it requires a defined reward function and environment that are non-trivial to specify for reputation events. A more academically defensible approach:

**Recommended alternative: Unsupervised/semi-supervised event detection** using:

* **Twitter volume peaks as event proxies**: Adapt the *event study* methodology from finance — identify events as statistically significant spikes in discussion volume (e.g., >2 standard deviations above the rolling 7-day baseline). This is well-validated in the literature.

> \*"We formalize the procedure by adapting the well-known 'event study' from economics and finance to the analysis of Twitter data. This allows us to automatically identify events as Twitter volume peaks, to compute the prevailing sentiment... and to relate them to stock returns." (Ranco et al., PMC4577113)\*

* **BERTopic or LDA** for topic clustering around volume peaks — to categorize the *type* of reputation event (product, executive, regulatory, legal)
* **Named Entity Recognition (NER)** using spaCy or fine-tuned BERT-NER to anchor events to specific companies, executives, and products

### 4.2 Where RL Adds Value (Revised Application)

RL is better positioned as a **response optimization engine** in Stage 6 — learning an optimal intervention strategy (when and how to respond to a reputation event) based on reward signals derived from post-intervention sentiment recovery trajectories. This is a novel contribution and methodologically sound.

\---

## Stage 5: Causal \& Correlation Analysis

This stage answers the core research question: do online signals *predict* (and potentially *cause*) stock price movements within the 6–24 hour window?

### 5.1 Granger Causality Testing

Test whether lagged sentiment scores Granger-cause stock Abnormal Returns at 1h, 3h, 6h, 12h, and 24h lags. This is the standard statistical framework for this type of relationship.

> \*Granger causality analysis applied to Meta's media sentiment and stock prices (2019–2024) found that sentiment scores have strong predictive power for short-term stock price movements at 1–2 month lags — this study sharpens the analysis to intraday horizons (University of Agora, 2024).\*

> \*The FinXABSA framework applies Granger causality to aspect-level sentiment and stock prices, finding explainable and robust statistical relationships between specific financial aspects and equity returns (arXiv:2303.02563).\*

**Implementation notes**:

* Test for stationarity first (ADF test) on both sentiment and return time series
* Use Vector Autoregression (VAR) to model bidirectional dependencies
* Apply rolling-window Granger causality to detect time-varying causal structure (not static over the full period)

### 5.2 Event Study — Abnormal Returns

For each detected reputation event:

* Define event window: \[t-1h, t+24h]
* Define estimation window: \[t-168h, t-2h] (7 days pre-event)
* Compute Cumulative Abnormal Returns (CAR) = actual returns − expected returns (CAPM benchmark)
* Regress CAR on sentiment velocity, volume spike, and source diversity at multiple lags

### 5.3 Cross-Correlation Analysis

Compute Pearson cross-correlation between hourly sentiment time series and stock return series at lags {0, 1, 2, 3, 6, 12, 24} hours to identify optimal predictive lag structure without assuming causality.

\---

## Stage 6: Prediction Model

### 6.1 Multimodal Feature Fusion

Combine:

* Sentiment score time series (from Stage 3 winning model)
* Engagement features (DV, SV, ER, NSI)
* Technical stock indicators (RSI, MACD, Bollinger Bands)
* Event type dummy variables (from Stage 4 classification)

> \*A FinBERT + XGBoost multimodal framework fusing sentiment signals with technical indicators achieves high correlation (R² = 0.76) between sentiment and market returns and provides SHAP-based feature attribution for interpretability (MDPI Mathematics, DOI: 10.3390/math13172747, 2025).\*

### 6.2 Prediction Architectures

* **XGBoost** with SHAP interpretability: strong baseline for tabular feature fusion
* **Stacked LSTM** with sliding window (60-period input): captures temporal sentiment momentum
* **Hybrid LSTM–Random Forest** ensemble: validated in recent financial sentiment literature

> \*A hybrid LSTM–Random Forest framework for stock market prediction integrating generative sentiment signals with historical market data showed enhanced accuracy across multiple industry sectors (Khalil, 2026, Journal of Modelling in Management).\*

### 6.3 Evaluation Metrics

* **Directional accuracy** (did the model correctly predict positive/negative price movement?): most practically relevant
* **RMSE, MAE** for magnitude prediction
* **Sharpe ratio** of a simulated trading strategy driven by model signals (external validity)
* **Wilcoxon signed-rank test** to confirm that performance improvements over baselines are statistically significant

\---

## Stage 7: Visualization \& Interpretability

* **SHAP** (SHapley Additive Explanations): decompose each prediction into feature attributions — critical for academic transparency and for communicating which signals drive reputation-stock linkages
* **Temporal heatmaps**: sentiment intensity vs. time vs. platform source
* **Event timelines**: overlay sentiment velocity with stock price, annotated by detected events
* **Interactive dashboard** (Plotly/Dash or Streamlit): for real-time monitoring demonstration

\---

## Methodological Gaps to Address Explicitly

The following are known limitations that strengthen the study if addressed proactively:

**1. The non-stationarity problem**: Sentiment and stock time series are both highly non-stationary. All models must account for concept drift — the statistical properties of the relationship between sentiment and price change over time. Use rolling-window retraining or adaptive models rather than a single static trained model.

**2. The confounding problem**: External macroeconomic events (rate decisions, geopolitical shocks) move stock prices independently of reputation signals. Include macro controls (VIX, Fed announcement calendar) and use abnormal returns rather than raw returns to partial these out.

**3. The platform selection bias problem**: Monitoring Twitter and Reddit captures a non-representative slice of stakeholder opinion. Dark social (private channels, closed forums) is unobserved. Acknowledge this explicitly as a limitation and discuss how latent variable models could theoretically address it in future work.

**4. The directionality ambiguity**: Granger causality does not imply true causality. Stock price movements can generate media coverage rather than the reverse. Discuss this explicitly and treat findings as predictive associations with causal interpretation requiring additional identification.

\---

## Summary Pipeline Diagram

```
RAW DATA (Social Media + News + Stock Prices)
         │
         ▼
BOT FILTERING (Ensemble Classifier: RF + XGBoost + LR)
         │
         ▼
TEXT PREPROCESSING (Noise removal → Emoji conversion → Normalization → Tokenization)
         │
         ▼
SENTIMENT ANALYSIS (VADER baseline → BERT → RoBERTa → DistilBERT → FinBERT → Hybrid/Ensemble)
         │
         ▼
SIGNAL CONSTRUCTION (Volume, Velocity, Engagement, NSI, Source Diversity)
         │
         ▼
EVENT DETECTION (Volume spike detection + BERTopic clustering + NER entity anchoring)
         │
         ├──────────────────────────────────────────────┐
         ▼                                              ▼
CAUSAL ANALYSIS                               PREDICTION MODEL
(Granger causality, VAR,                      (XGBoost + SHAP,
 Event study CAR,                              Stacked LSTM,
 Rolling cross-correlation)                    Hybrid LSTM-RF ensemble)
         │                                              │
         └──────────────────┬───────────────────────────┘
                            ▼
               EVALUATION \& VISUALIZATION
               (SHAP, RMSE, Directional Accuracy,
                Temporal Heatmaps, Interactive Dashboard)
```

\---

## Key Academic References

|Reference|Relevance|
|-|-|
|Zhang et al. (2024). *Sentiment Analysis in the Era of LLMs: A Reality Check.* NAACL Findings. DOI: 10.18653/v1/2024.findings-naacl.246|LLM vs. SLM benchmark for sentiment — model selection justification|
|Zaâbi \& Boukhris (2025). *Enhancing Financial Sentiment with FinBERT and RoBERTa.* Springer LNBIP Vol. 560.|FinRoBERT-FSA hybrid — most directly analogous architecture|
|Ranco et al. (2015). *Effects of Twitter Sentiment on Stock Price Returns.* PMC4577113|Event study methodology + Granger causality for Twitter-stock link|
|Khalil (2026). *AI-driven sentiment analysis in financial markets.* Journal of Modelling in Management. DOI: 10.1108/JM2-08-2025-0415|Hybrid LSTM-RF framework + multisource dataset design|
|MDPI Mathematics (2025). *Stock Price Prediction with FinBERT + SHAP + XGBoost.* DOI: 10.3390/math13172747|Multimodal fusion + SHAP interpretability|
|Frontiers in AI Applications (2025). *Stacked LSTM for short-term financial prediction.*|Sliding window LSTM architecture + statistical validation methodology|
|IEEE Access (2024). DOI: 10.1109/ACCESS.2024.3430859|Bot detection preprocessing — BiGRU-LSTM hybrid|
|Herrera-Poyatos et al. (2025). *Model uncertainty in LLM sentiment analysis.* Frontiers in AI. DOI: 10.3389/frai.2025.1609097|Uncertainty quantification — why single-model approach is insufficient|
|University of Agora (2024). *Media sentiment and stock prices: temporal dynamics and Granger causality.*|Granger causality methodology for sentiment-price time series|

\---

*Research Methodology Draft — PhD Data Science | May 2026*

