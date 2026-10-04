"""skills.py — the vocabulary used to compare a posting with a resume.

A posting and a resume are both reduced to the set of vocabulary terms they
mention. Matching then works on those sets, so "PyTorch" in a posting lines up
with "PyTorch" on a resume no matter how either sentence is worded.

Each entry is  canonical name -> regular expression.  Patterns are matched
without regard to case unless the name is listed in CASE_SENSITIVE. To teach the
matcher a new skill, add one line here.
"""
from __future__ import annotations

import re
from typing import Dict, Set

VOCAB: Dict[str, str] = {
    # ── languages ──
    "Python": r"\bpython\b",
    "C++": r"\bc\+\+|\bcpp\b",
    "C": r"(?<![\w+#.])C(?![\w+#]|\.\w)(?=\s*(?:,|/|\)|;|and\b|or\b|programming|language|$))",
    "C#": r"\bc#|\.net\b",
    "Java": r"\bjava\b(?!\s*script)",
    "JavaScript": r"\bjavascript\b|\bnode\.?js\b",
    "TypeScript": r"\btypescript\b",
    "Go": r"\b[Gg]olang\b|(?<=[,/(] )Go\b|(?<=\bor )Go\b|(?<=\band )Go\b|\bGo\b(?=\s*(?:,|/|\)|programming|lang))",
    "Rust": r"\brust\b",
    "R": r"(?<![\w&])R(?![\w&])(?=\s*(?:,|/|\)|;|and\b|or\b|programming|studio|$))",
    "MATLAB": r"\bmatlab\b",
    "Julia": r"\bjulia\b(?=\s*(?:,|/|\)|and\b|or\b|programming|lang))",
    "Scala": r"\bscala\b",
    "Kotlin": r"\bkotlin\b",
    "Swift": r"\bswift\b(?=\s*(?:,|/|\)|and\b|or\b|ui|programming))",
    "SQL": r"\bsql\b",
    "q/KDB+": r"\bkdb\+?|\bq/kdb|\bkdb/q",
    "VBA": r"\bvba\b",
    "Bash": r"\bbash\b|shell script",
    "OCaml": r"\bocaml\b",
    "Verilog": r"\b(system)?verilog\b|\bvhdl\b",
    "CUDA": r"\bcuda\b",
    "HTML/CSS": r"\bhtml\b|\bcss\b",
    # ── ML frameworks and tools ──
    "PyTorch": r"\bpytorch\b|\btorch\b",
    "TensorFlow": r"\btensorflow\b|\bkeras\b",
    "JAX": r"\bjax\b",
    "scikit-learn": r"scikit.?learn|\bsklearn\b",
    "NumPy": r"\bnumpy\b",
    "SciPy": r"\bscipy\b",
    "pandas": r"\bpandas\b",
    "HuggingFace": r"hugging\s?face|\btransformers library\b",
    "ONNX": r"\bonnx\b",
    "TensorRT": r"\btensorrt\b",
    "MLflow": r"\bmlflow\b|weights\s*(?:&|and)\s*biases|\bwandb\b",
    "XGBoost": r"\bxgboost\b|\blightgbm\b|gradient boost",
    "OpenCV": r"\bopencv\b",
    "Ray": r"\bray\b(?=\s*(?:,|/|\)|rllib|tune|serve|cluster))",
    # ── ML areas ──
    "machine learning": r"machine learning|\bML\b",
    "deep learning": r"deep learning|neural network",
    "reinforcement learning": r"reinforcement learning|\bRL\b|\bppo\b|\bdqn\b|policy gradient|actor.critic",
    "imitation learning": r"imitation learning|behaviou?r(al)? cloning|learning from demonstration",
    "diffusion models": r"diffusion (model|polic)|\bddpm\b|score.based|flow matching",
    "vision-language-action": r"vision.language.action|\bVLAs?\b|\bgr00t\b|\bopenvla\b|\brt-[12x]\b|\bpi.?0\b",
    "vision-language models": r"vision.language model|\bVLMs?\b|multimodal",
    "foundation models": r"foundation model",
    "LLM": r"\bLLMs?\b|large language model|\bgpt\b|language model",
    "fine-tuning": r"fine.?tun|\blora\b|\bqlora\b|\bpeft\b",
    "RAG": r"retrieval.augmented|\bRAG\b|vector (search|database|store)|\bpgvector\b|embedding",
    "agentic AI": r"\bagentic\b|ai agents?|llm agents?|multi.agent|tool use",
    "prompt engineering": r"prompt (engineering|design)|prompting",
    "NLP": r"\bNLP\b|natural language processing",
    "computer vision": r"computer vision|\bCV\b(?=\s*(?:,|/|and|or|models?|algorithms?))|image (classification|segmentation)|object detection",
    "transformers": r"\btransformers?\b|attention mechanism|\bvit\b|vision transformer",
    "CNN": r"\bCNNs?\b|convolutional",
    "RNN/LSTM": r"\bLSTMs?\b|\bRNNs?\b|recurrent neural",
    "autoencoders": r"auto.?encoder|\bVAEs?\b",
    "generative AI": r"generative (ai|model)|\bgen.?ai\b",
    "time series": r"time.series|forecasting model|demand forecasting",
    "feature engineering": r"feature engineering",
    "model optimization": r"model (optimization|compression)|quantization|pruning|distillation",
    "model evaluation": r"evaluation methodolog|model evaluation|ablation|benchmark(ing|s)?\b|experiment(al)? design",
    "hyperparameter tuning": r"hyper.?parameter",
    "MLOps": r"\bmlops\b|model (deployment|serving)|ml (infrastructure|platform|pipelines?)",
    "inference": r"\binference\b",
    "GPU computing": r"\bGPUs?\b|gpu.accelerat",
    "distributed training": r"distributed training|multi.gpu|large.scale training",
    "recommender systems": r"recommend(er|ation) (system|model)|ranking model",
    "anomaly detection": r"anomaly detection",
    "Bayesian methods": r"\bbayesian\b|probabilistic (model|programming)",
    "optimization": r"\b(convex|numerical|combinatorial|mathematical) optimization|operations research|linear programming",
    "quantum computing": r"\bquantum\b|\bpennylane\b|\bqiskit\b",
    # ── robotics ──
    "robotics": r"\brobot(ic|ics|s)?\b",
    "manipulation": r"robot(ic)? manipulat|manipulation (polic|task|skill|planning|research)|\bmanipulators?\b|\bgrasping\b|\bhandover|pick.and.place|dexterous|learned manipulation",
    "robot learning": r"robot learning|embodied (ai|intelligence)|learned (manipulation|polic)",
    "ROS": r"\bROS\s?2?\b|robot operating system",
    "SLAM": r"\bslam\b|visual odometry|localization and mapping",
    "motion planning": r"motion planning|path planning|trajectory (planning|optimization)",
    "controls": r"control (systems?|theory|algorithms?|engineer)|controls (engineer|software|algorithm)|\bMPC\b|model predictive|\bPID\b|impedance control|feedback control|closed.loop control",
    "kinematics": r"kinematics|dynamics model|rigid.body",
    "perception": r"\bperception\b|sensor fusion|point clouds?|\blidar\b|depth (camera|sensing)",
    "state estimation": r"state estimation|kalman filter",
    "simulation": r"\bsimulat(ion|or)s?\b|sim.?(2|to).?real|real.?(2|to).?sim|digital twin",
    "economics": r"\beconomics\b|\beconomist\b",
    "Isaac Sim": r"isaac (sim|lab|gym)|\bomniverse\b",
    "MuJoCo": r"\bmujoco\b|\bgazebo\b|\bpybullet\b|\bdrake\b",
    "LeRobot": r"\blerobot\b",
    "real-time systems": r"real.time (system|control|software|inference)|closed.loop|hard real.time",
    "robot hardware": r"robot(ic)? (arm|hardware|platform)s?|\bfranka\b|\bur5\b|\bkuka\b|end.effector|gripper|actuator",
    "autonomous systems": r"autonomous (system|vehicle|driving|robot|flight|navigation)|autonomy (stack|software|team|engineer|research|algorithms?)|self.driving",
    "aerospace": r"aerospace|spacecraft|satellite|in.space|\bGNC\b|orbital",
    "teleoperation": r"tele.?operat|data collection (pipeline|system)",
    "embedded": r"\bembedded\b|\bfirmware\b|micro.?controller|\brtos\b",
    # ── quant finance ──
    "quantitative research": r"quantitative (research|analy|strateg|model|trading|finance)|\bquant\b",
    "trading": r"\btrading\b|\btraders?\b|market making|order execution|execution algorithms?",
    "backtesting": r"back.?test",
    "market data": r"market data|tick data|order book|\bfeed handlers?\b",
    "market microstructure": r"microstructure",
    "options": r"\boptions?\b(?=\s*(?:pricing|trading|market|and|,|/))|derivatives|volatility|\bgreeks\b",
    "futures": r"\bfutures\b",
    "equities": r"\bequities\b|equity (trading|markets?|research|derivatives|options|volatility|index)",
    "fixed income": r"fixed income|interest rate (derivatives|swaps|products)|rates trading|credit (risk|trading)|\btreasur(y|ies) (market|trading)",
    "risk management": r"risk (management|model|analy)|\bVaR\b",
    "portfolio": r"portfolio (construction|optimization|management)|asset allocation",
    "alpha research": r"alpha (research|generation|signals?)|generat\w+ alpha|signal (research|generation)|trading signals?|systematic (trading|strateg|research)|stat(istical)? arb",
    "transaction costs": r"transaction cost|slippage|market impact",
    "stochastic calculus": r"stochastic (calculus|process|differential|control|model)|\bito\b|brownian|\bSDEs?\b",
    "probability": r"\bprobability\b|markov|monte carlo|\bMCMC\b",
    "statistics": r"\bstatistic(s|al)\b|regression (model|analysis)|linear regression|hypothesis test|econometric",
    "linear algebra": r"linear algebra|matrix (decomposition|factorization)",
    "financial markets": r"financial markets?|capital markets|asset class|hedge fund|prop(rietary)? trading",
    "low-latency": r"low.latency|high.frequency|\bHFT\b|ultra.low",
    "Excel": r"\bexcel\b",
    "Bloomberg": r"\bbloomberg\b",
    # ── data and infrastructure ──
    "PostgreSQL": r"postgres(ql)?|\bmysql\b|\bmssql\b|sql server|relational database",
    "NoSQL": r"\bnosql\b|\bmongodb\b|\bcassandra\b|\bdynamodb\b|\bredis\b",
    "time series databases": r"time.series database|\binfluxdb\b|\btimescale\b|\bclickhouse\b",
    "Spark": r"\bspark\b|\bpyspark\b|\bhadoop\b|\bdatabricks\b",
    "Kafka": r"\bkafka\b|message queue|\bpub.?sub\b|\bzmq\b|\bzeromq\b|\brabbitmq\b",
    "data pipelines": r"data (pipeline|infrastructure|platform|ingestion)s?|\bETL\b|\bairflow\b|\bdbt\b",
    "data warehousing": r"data warehouse|\bsnowflake\b|\bbigquery\b|\bredshift\b",
    "streaming": r"\bstreaming\b|web.?sockets?|real.time data",
    "REST APIs": r"\brest(ful)?\b(?=\s*api)|\bapis?\b",
    "Docker": r"\bdocker\b|container(s|ized|ization)\b",
    "Kubernetes": r"\bkubernetes\b|\bk8s\b",
    "AWS": r"\bAWS\b|amazon web services|\bEC2\b|\bS3\b",
    "Azure": r"\bazure\b",
    "GCP": r"\bGCP\b|google cloud",
    "cloud": r"\bcloud\b",
    "Linux": r"\blinux\b|\bunix\b",
    "Git": r"\bgit\b|\bgithub\b|\bgitlab\b|version control",
    "CI/CD": r"\bCI/CD\b|continuous integration|\bjenkins\b|github actions",
    "distributed systems": r"distributed (system|computing)|scalab(le|ility)|high.availability|microservices",
    "networking": r"computer network|network(ing)? (protocols?|stack|engineer|software|infrastructure)|\bTCP\b|mesh network",
    "virtualization": r"virtuali[sz]ation|\bproxmox\b|\bvmware\b|hypervisor",
    "monitoring": r"observability|\bgrafana\b|\bprometheus\b|\balerting\b|monitoring (system|tool|infrastructure|and alerting)|system monitoring",
    "testing": r"unit test|test (automation|harness|framework)|(parity|test) harness|validation tooling|\bpytest\b|\bQA\b",
    "performance": r"performance (optimization|tuning|engineering)|\bprofiling\b|high.performance (computing|code|systems?)|\bHPC\b",
    "multithreading": r"multi.?thread|concurren(t|cy)|parallel (computing|programming)",
    "algorithms": r"\balgorithms?\b|data structures",
    "software engineering": r"software (engineering|development|design)|object.oriented|\bOOP\b|code review",
    "backend": r"\bback.?end\b|server.side",
    "frontend": r"\bfront.?end\b|\breact\b|\bangular\b|\bvue\b",
    "full stack": r"full.?stack",
    "web frameworks": r"\bfastapi\b|\bflask\b|\bdjango\b|\bspring\b",
    "mobile": r"\bios\b|\bandroid\b|mobile (app|development)",
    "security": r"cyber.?security|(information|application|network|cloud|product) security|security (engineer|research|software|vulnerabilit)|cryptograph|penetration test",
    "compilers": r"\bcompilers?\b|\bllvm\b",
    "operating systems": r"operating systems?|\bkernel\b",
    "databases": r"\bdatabases?\b",
    # ── data science ──
    "data science": r"data scien(ce|tist)",
    "data analysis": r"data analy(sis|tics|st)|analytics (engineer|platform|team)|exploratory analysis",
    "visualization": r"visuali[sz]ation|\btableau\b|power\s?bi|\bmatplotlib\b|dashboards?",
    "A/B testing": r"a/b test|experimentation platform|causal inference",
    "signal processing": r"signal processing|\bDSP\b|sensor data",
    "biomedical": r"biomedical|medical devices?|physiological|clinical (data|trial|research)|\bFDA\b|glucose",
    # ── research and level ──
    "PhD": r"\bph\.?\s?d\b|doctoral|doctorate",
    "publications": r"publication|published|peer.reviewed|\b(neurips|icml|iclr|cvpr|iccv|corl|icra|iros|rss|aaai|acl|emnlp)\b|top.tier (conference|venue)",
    "research": r"\bresearch\b",
    "mathematics": r"\bmathematic(s|al)\b|applied math",
    "technical leadership": r"\b(tech(nical)?|team) lead\b|lead(ing)? a team|led a team",
}

# A term on the left, when it is on the RESUME, also counts as the terms on the
# right. A resume that lists PPO has reinforcement learning, even if a posting
# only says "reinforcement learning". This is applied to the resume side only.
IMPLIES: Dict[str, list] = {
    "PyTorch": ["deep learning", "machine learning", "Python"],
    "TensorFlow": ["deep learning", "machine learning", "Python"],
    "scikit-learn": ["machine learning", "Python"],
    "NumPy": ["Python"], "SciPy": ["Python"], "pandas": ["Python"],
    "reinforcement learning": ["machine learning"],
    "imitation learning": ["machine learning", "robot learning"],
    "diffusion models": ["deep learning", "generative AI"],
    "vision-language-action": ["robot learning", "foundation models",
                               "vision-language models", "transformers"],
    "fine-tuning": ["LLM"], "RAG": ["LLM"], "HuggingFace": ["LLM", "transformers"],
    "LLM": ["NLP", "generative AI"],
    "manipulation": ["robotics"], "SLAM": ["robotics", "perception"],
    "LeRobot": ["robotics", "robot learning"], "Isaac Sim": ["simulation", "robotics"],
    "robot hardware": ["robotics"],
    "q/KDB+": ["time series databases", "databases"],
    "PostgreSQL": ["SQL", "databases"],
    "backtesting": ["quantitative research"],
    "market microstructure": ["financial markets", "quantitative research"],
    "market data": ["financial markets"],
    "options": ["financial markets"], "futures": ["financial markets"],
    "stochastic calculus": ["probability", "mathematics"],
    "Docker": ["Linux"],
    "AWS": ["cloud"], "Azure": ["cloud"],
    "C++": ["software engineering"], "Python": ["software engineering"],
}

# These three are a bare capital letter or word, so they are matched as written.
_STRICT = {"C", "R", "Go"}
# Acronyms inside the other patterns (ML, RAG, CV ...) also count only when
# capitalised. Lowercase "rag" or "cv" in running text is an ordinary word.
_ACRONYM = re.compile(r"\\b([A-Z][A-Z0-9/]{1,5}(?:s\?)?)\\b")


def _compile(name: str, pattern: str) -> "re.Pattern":
    if name in _STRICT:
        return re.compile(pattern)
    return re.compile(_ACRONYM.sub(lambda m: "(?-i:\\b" + m.group(1) + "\\b)", pattern), re.I)


_COMPILED = {name: _compile(name, pat) for name, pat in VOCAB.items()}


def extract(text: str) -> Set[str]:
    """Every vocabulary term mentioned in `text`."""
    if not text:
        return set()
    return {name for name, pat in _COMPILED.items() if pat.search(text)}


def expand(terms: Set[str]) -> Set[str]:
    """Add what the terms imply. Used for the resume, never for a posting."""
    out = set(terms)
    grew = True
    while grew:
        grew = False
        for t in list(out):
            for extra in IMPLIES.get(t, []):
                if extra not in out:
                    out.add(extra)
                    grew = True
    return out
