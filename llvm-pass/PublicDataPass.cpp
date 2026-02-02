#include "llvm/ADT/DenseMap.h"
#include "llvm/ADT/DenseSet.h"
#include "llvm/ADT/StringMap.h"
#include "llvm/ADT/SmallString.h"
#include "llvm/ADT/StringRef.h"
#include "llvm/IR/Argument.h"
#include "llvm/IR/Constants.h"
#include "llvm/IR/Value.h"
#include "llvm/IR/Function.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/InstrTypes.h"
#include "llvm/IR/PassManager.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Passes/PassPlugin.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/raw_ostream.h"

#include <cstdio>
#include <functional>
#include <memory>
#include <string>
#include <vector>

using namespace llvm;

namespace {

static cl::opt<std::string> TraceOut(
  "public-data-trace",
  cl::desc("Write NDJSON trace to this path"),
  cl::init("")
);
static cl::opt<std::string> TraceIndexOut(
  "public-data-trace-index",
  cl::desc("Write NDJSON trace index to this path"),
  cl::init("")
);
static cl::opt<bool> TraceTypes(
  "public-data-trace-types",
  cl::desc("Include type strings in trace output"),
  cl::init(false)
);
static cl::opt<unsigned> MaxInst(
  "public-data-max-inst",
  cl::desc("Maximum trace instructions emitted per function (0 disables)"),
  cl::init(0)
);
static cl::opt<std::string> CfgOut(
  "public-data-cfg",
  cl::desc("Write NDJSON CFG/path info to this path"),
  cl::init("")
);
static cl::opt<unsigned> MaxPaths(
  "public-data-max-paths",
  cl::desc("Maximum number of paths to emit per function (0 disables)"),
  cl::init(200)
);
static cl::opt<unsigned> MaxPathDepth(
  "public-data-max-path-depth",
  cl::desc("Maximum basic blocks per path"),
  cl::init(256)
);
static cl::opt<unsigned> MaxLoopIters(
  "public-data-max-loop-iters",
  cl::desc("Maximum loop iterations per block on a path"),
  cl::init(0)
);
static cl::opt<std::string> PathCondFormat(
  "public-data-path-cond-format",
  cl::desc("Path condition format: string|json|both"),
  cl::init("string")
);
static cl::opt<bool> IncludePpSeq(
  "public-data-path-include-pp-seq",
  cl::desc("Include instruction-level pp_seq for each path record"),
  cl::init(false)
);
static cl::opt<bool> EmitPpCoverage(
  "public-data-pp-coverage",
  cl::desc("Emit pp_coverage records mapping pp -> path ids"),
  cl::init(false)
);
static cl::opt<unsigned> MaxPpPathIds(
  "public-data-max-pp-path-ids",
  cl::desc("Max path ids listed per pp_coverage record"),
  cl::init(64)
);
static cl::opt<bool> Quiet(
  "public-data-quiet",
  cl::desc("Suppress debug output"),
  cl::init(false)
);
static cl::opt<bool> Verbose(
  "public-data-verbose",
  cl::desc("Enable verbose debug output"),
  cl::init(false)
);

// Build a stable program point label for an instruction.
// Inputs: function name, basic block label, instruction index.
// Output: "fn:bb:iN".
static std::string programPointLabel(StringRef fnName, StringRef bbLabel,
                                      int instIndex) {
  std::string s;
  raw_string_ostream os(s);
  os << fnName << ":" << bbLabel << ":i" << instIndex;
  return os.str();
}

// Escape a string for safe JSON output.
// Input: raw string.
// Output: escaped string (without surrounding quotes).
static std::string escapeJson(StringRef s) {
  std::string out;
  out.reserve(s.size());
  for (char c : s) {
    switch (c) {
      case '\\': out += "\\\\"; break;
      case '"': out += "\\\""; break;
      case '\n': out += "\\n"; break;
      case '\r': out += "\\r"; break;
      case '\t': out += "\\t"; break;
      default:
        if (static_cast<unsigned char>(c) < 0x20) {
          char buf[7];
          std::snprintf(buf, sizeof(buf), "\\u%04x",
                        static_cast<unsigned char>(c));
          out += buf;
        } else {
          out += c;
        }
    }
  }
  return out;
}

// Emit a JSON string literal to an output stream.
static void emitJsonString(raw_ostream &os, StringRef s) {
  os << "\"" << escapeJson(s) << "\"";
}

// Open (or return) the trace NDJSON stream. Returns nullptr if disabled.
static raw_fd_ostream *getTraceStream() {
  if (TraceOut.empty()) return nullptr;
  static std::unique_ptr<raw_fd_ostream> trace;
  if (!trace) {
    std::error_code ec;
    trace = std::make_unique<raw_fd_ostream>(TraceOut, ec, sys::fs::OF_Text);
    if (ec) {
      errs() << "Failed to open trace file: " << ec.message() << "\n";
      trace.reset();
      return nullptr;
    }
  }
  return trace.get();
}

// Open (or return) the trace index stream. Returns nullptr if disabled.
static raw_fd_ostream *getTraceIndexStream() {
  if (TraceIndexOut.empty()) return nullptr;
  static std::unique_ptr<raw_fd_ostream> traceIndex;
  if (!traceIndex) {
    std::error_code ec;
    traceIndex = std::make_unique<raw_fd_ostream>(TraceIndexOut, ec, sys::fs::OF_Text);
    if (ec) {
      errs() << "Failed to open trace index file: " << ec.message() << "\n";
      traceIndex.reset();
      return nullptr;
    }
  }
  return traceIndex.get();
}

// Open (or return) the CFG/path NDJSON stream. Returns nullptr if disabled.
static raw_fd_ostream *getCfgStream() {
  if (CfgOut.empty()) return nullptr;
  static std::unique_ptr<raw_fd_ostream> cfg;
  if (!cfg) {
    std::error_code ec;
    cfg = std::make_unique<raw_fd_ostream>(CfgOut, ec, sys::fs::OF_Text);
    if (ec) {
      errs() << "Failed to open CFG file: " << ec.message() << "\n";
      cfg.reset();
      return nullptr;
    }
  }
  return cfg.get();
}

// Emit a JSON array of strings.
static void emitJsonStringArray(raw_ostream &os,
                                const std::vector<std::string> &vals) {
  os << "[";
  for (size_t i = 0; i < vals.size(); ++i) {
    if (i) os << ",";
    emitJsonString(os, vals[i]);
  }
  os << "]";
}

// Convert an LLVM type to a printed string form.
static std::string typeToString(const Type *Ty) {
  std::string s;
  raw_string_ostream os(s);
  if (Ty) {
    Ty->print(os);
  } else {
    os << "<null>";
  }
  return os.str();
}

// Print transmitter info to stderr for debugging.
static void printTransmitter(const Instruction &I, StringRef kind,
                             const Value *operand) {
  errs() << "  [TX] " << kind << " @ " << I.getFunction()->getName() << " : ";
  I.print(errs());
  errs() << "\n";
  errs() << "      operand: ";
  if (operand) operand->print(errs());
  else errs() << "<null>";
  errs() << "\n";
}

// Transmitter metadata (kind and operand index).
struct TxInfo {
  bool present = false;
  const char *kind = nullptr;
  int operandIndex = -1;
};

// Identify transmitters per project sheet (minimum set).
// Output: TxInfo with present=false if not a transmitter.
static TxInfo getTransmitterInfo(const Instruction &I) {
  TxInfo info;
  if (isa<LoadInst>(I)) {
    info.present = true;
    info.kind = "load.addr";
    info.operandIndex = 0;
  } else if (isa<StoreInst>(I)) {
    info.present = true;
    info.kind = "store.addr";
    info.operandIndex = 1;
  } else if (auto *BI = dyn_cast<BranchInst>(&I)) {
    if (BI->isConditional()) {
      info.present = true;
      info.kind = "br.cond";
      info.operandIndex = 0;
    }
  } else if (isa<SwitchInst>(I)) {
    info.present = true;
    info.kind = "switch.cond";
    info.operandIndex = 0;
  } else if (isa<IndirectBrInst>(I)) {
    info.present = true;
    info.kind = "indirectbr.target";
    info.operandIndex = 0;
  }
  return info;
}

// Convert an integer constant to a stable ID string.
static std::string constIntId(const ConstantInt &CI) {
  SmallString<32> buf;
  CI.getValue().toString(buf, 10, true, false);
  return "const:i" + std::to_string(CI.getBitWidth()) + ":" +
         std::string(buf.str());
}

// Convert a floating-point constant to a stable ID string.
static std::string constFpId(const ConstantFP &CFP) {
  SmallString<32> buf;
  CFP.getValueAPF().toString(buf);
  return "const:fp:" + std::string(buf.str());
}

// Convert an LLVM constant to a stable ID string.
static std::string getConstantId(const Constant &C) {
  if (auto *CI = dyn_cast<ConstantInt>(&C)) {
    return constIntId(*CI);
  }
  if (auto *CFP = dyn_cast<ConstantFP>(&C)) {
    return constFpId(*CFP);
  }
  if (isa<ConstantPointerNull>(C)) {
    return "const:null";
  }
  if (isa<UndefValue>(C)) {
    return "const:undef";
  }
  if (isa<PoisonValue>(C)) {
    return "const:poison";
  }

  std::string s;
  raw_string_ostream os(s);
  C.print(os);
  return "const:" + std::string(os.str());
}

// Convert an LLVM Value to a stable ID string.
static std::string getValueId(const Value *V,
                              DenseMap<const Value *, std::string> &ids,
                              unsigned &nextId) {
  if (auto *C = dyn_cast<Constant>(V)) {
    return getConstantId(*C);
  }
  if (auto *A = dyn_cast<Argument>(V)) {
    if (A->hasName()) return A->getName().str();
    return "arg" + std::to_string(A->getArgNo());
  }
  if (V->hasName()) return V->getName().str();

  auto it = ids.find(V);
  if (it != ids.end()) return it->second;
  std::string id = "v" + std::to_string(nextId++);
  ids[V] = id;
  return id;
}

// Build a string constraint for the switch default branch.
static std::string buildSwitchDefaultCond(
  const SwitchInst &SI,
  const std::string &condId,
  DenseMap<const Value *, std::string> &ids,
  unsigned &nextId) {
  std::string s;
  for (auto &Case : SI.cases()) {
    std::string caseVal = getValueId(Case.getCaseValue(), ids, nextId);
    if (!s.empty()) s += " && ";
    s += condId;
    s += "!=";
    s += caseVal;
  }
  if (s.empty()) {
    s = condId + "!=<any>";
  }
  return s;
}

// Decision metadata for a branch along a path.
struct Decision {
  std::string pp;
  std::string kind;
  std::string cond;
  std::string succ;
  std::string sense;
  std::string caseValue;
  bool isDefault = false;
  std::string target;
};

// Structured condition expression for JSON path conditions.
struct CondExpr {
  std::string op;
  std::string lhs;
  std::string rhs;
  std::vector<CondExpr> terms;
};

// Build a comparison expression node (== or !=).
static CondExpr makeCmp(StringRef op, StringRef lhs, StringRef rhs) {
  CondExpr e;
  e.op = op.str();
  e.lhs = lhs.str();
  e.rhs = rhs.str();
  return e;
}

// Build an "and" expression node.
static CondExpr makeAnd(std::vector<CondExpr> terms) {
  CondExpr e;
  e.op = "and";
  e.terms = std::move(terms);
  return e;
}

// Emit a JSON condition expression to the output stream.
static void emitCondExpr(raw_ostream &os, const CondExpr &e) {
  os << "{";
  os << "\"op\":";
  emitJsonString(os, e.op);
  if (e.op == "and") {
    os << ",\"terms\":[";
    for (size_t i = 0; i < e.terms.size(); ++i) {
      if (i) os << ",";
      emitCondExpr(os, e.terms[i]);
    }
    os << "]";
  } else {
    os << ",\"lhs\":";
    emitJsonString(os, e.lhs);
    os << ",\"rhs\":";
    emitJsonString(os, e.rhs);
  }
  os << "}";
}

// Emit a JSON decision record to the output stream.
static void emitDecision(raw_ostream &os, const Decision &d) {
  os << "{";
  os << "\"pp\":";
  emitJsonString(os, d.pp);
  os << ",\"kind\":";
  emitJsonString(os, d.kind);
  os << ",\"succ\":";
  emitJsonString(os, d.succ);
  if (!d.cond.empty()) {
    os << ",\"cond\":";
    emitJsonString(os, d.cond);
  }
  if (!d.sense.empty()) {
    os << ",\"sense\":";
    emitJsonString(os, d.sense);
  }
  if (!d.caseValue.empty()) {
    os << ",\"case\":";
    emitJsonString(os, d.caseValue);
  }
  if (d.isDefault) {
    os << ",\"default\":true";
  }
  if (!d.target.empty()) {
    os << ",\"target\":";
    emitJsonString(os, d.target);
  }
  os << "}";
}

// Emit a trace index record (pp -> trace line).
static void emitTraceIndexRecord(raw_ostream &os, StringRef fn, StringRef bb,
                                 StringRef pp, StringRef op, StringRef defId,
                                 unsigned line) {
  os << "{";
  os << "\"kind\":\"trace_index\",\"fn\":";
  emitJsonString(os, fn);
  os << ",\"bb\":";
  emitJsonString(os, bb);
  os << ",\"pp\":";
  emitJsonString(os, pp);
  os << ",\"op\":";
  emitJsonString(os, op);
  os << ",\"def\":";
  if (!defId.empty()) emitJsonString(os, defId);
  else os << "null";
  os << ",\"line\":" << line;
  os << "}\n";
}

struct PublicDataPass : PassInfoMixin<PublicDataPass> {
  static bool isRequired() { return true; }  // <--- add this

  // Main pass entry point: emits trace and CFG records for one function.
  PreservedAnalyses run(Function &F, FunctionAnalysisManager &) {
    bool quiet = Quiet;
    bool verbose = Verbose && !Quiet;

    if (!quiet) {
      errs() << "== PublicDataPass on function: " << F.getName() << " ==\n";
    }

    DenseMap<const BasicBlock *, unsigned> bbIndex;
    DenseMap<const BasicBlock *, std::string> bbLabels;
    unsigned bbCounter = 0;
    for (auto &BB : F) {
      bbIndex[&BB] = bbCounter++;
      std::string label =
        BB.hasName() ? BB.getName().str()
                     : ("bb" + std::to_string(bbIndex[&BB]));
      bbLabels[&BB] = label;
    }

    DenseMap<const Value *, std::string> valueIds;
    unsigned nextValueId = 0;
    DenseMap<const Instruction *, std::string> instPP;
    DenseMap<const BasicBlock *, std::vector<std::string>> bbPpSeq;
    DenseMap<const BasicBlock *, std::string> termPP;
    unsigned instCount = 0;
    unsigned txCount = 0;
    unsigned traceEmitted = 0;
    bool traceTruncated = false;
    unsigned traceLine = 0;

    raw_fd_ostream *trace = getTraceStream();
    raw_fd_ostream *traceIndex = getTraceIndexStream();
    raw_fd_ostream *cfg = getCfgStream();
    bool emitCondStr = true;
    bool emitCondJson = false;

    StringRef fmt = PathCondFormat;
    if (fmt == "json") {
      emitCondStr = false;
      emitCondJson = true;
    } else if (fmt == "both") {
      emitCondStr = true;
      emitCondJson = true;
    } else if (fmt == "string") {
      emitCondStr = true;
      emitCondJson = false;
    } else if (!fmt.empty()) {
      if (!quiet) {
        errs() << "Unknown -public-data-path-cond-format: " << fmt
               << " (defaulting to string)\n";
      }
      emitCondStr = true;
      emitCondJson = false;
    }

    for (auto &BB : F) {
      std::string bbLabel = bbLabels[&BB];
      int idx = 0;
      for (auto &I : BB) {
        std::string pp =
          programPointLabel(F.getName(), bbLabel, idx);
        instPP[&I] = pp;
        bbPpSeq[&BB].push_back(pp);
        if (I.isTerminator()) {
          termPP[&BB] = pp;
        }
        if (verbose) {
          errs() << "PP " << pp << " : ";
          I.print(errs());
          errs() << "\n";
        }

        TxInfo tx = getTransmitterInfo(I);
        if (tx.present && !quiet) {
          const Value *op = nullptr;
          if (tx.operandIndex >= 0 &&
              tx.operandIndex < static_cast<int>(I.getNumOperands())) {
            op = I.getOperand(tx.operandIndex);
          }
          printTransmitter(I, tx.kind, op);
        }
        if (tx.present) {
          txCount++;
        }

        if (trace) {
          if (MaxInst != 0 && traceEmitted >= MaxInst) {
            traceTruncated = true;
          } else {
          std::string opcode = I.getOpcodeName();
          bool hasDef = !I.getType()->isVoidTy();
          std::string defId = hasDef ? getValueId(&I, valueIds, nextValueId)
                                     : "";
          std::vector<std::string> uses;
          uses.reserve(I.getNumOperands());
          std::vector<std::string> useTypes;
          if (TraceTypes) {
            useTypes.reserve(I.getNumOperands());
          }
          bool isPhi = isa<PHINode>(I);
          for (const Use &U : I.operands()) {
            const Value *V = U.get();
            if (auto *BB = dyn_cast<BasicBlock>(V)) {
              if (!isPhi) continue;
              uses.push_back(bbLabels[BB]);
              if (TraceTypes) {
                useTypes.push_back(typeToString(V->getType()));
              }
              continue;
            }
            uses.push_back(getValueId(V, valueIds, nextValueId));
            if (TraceTypes) {
              useTypes.push_back(typeToString(V->getType()));
            }
          }

          *trace << "{";
          *trace << "\"fn\":";
          emitJsonString(*trace, F.getName());
          *trace << ",\"bb\":";
          emitJsonString(*trace, bbLabel);
          *trace << ",\"pp\":";
          emitJsonString(*trace, pp);
          *trace << ",\"op\":";
          emitJsonString(*trace, opcode);
          *trace << ",\"def\":";
          if (hasDef) emitJsonString(*trace, defId);
          else *trace << "null";
          *trace << ",\"uses\":[";
          for (size_t i = 0; i < uses.size(); ++i) {
            if (i) *trace << ",";
            emitJsonString(*trace, uses[i]);
          }
          *trace << "]";
          if (TraceTypes) {
            *trace << ",\"def_ty\":";
            if (hasDef) emitJsonString(*trace, typeToString(I.getType()));
            else *trace << "null";
            *trace << ",\"use_tys\":[";
            for (size_t i = 0; i < useTypes.size(); ++i) {
              if (i) *trace << ",";
              emitJsonString(*trace, useTypes[i]);
            }
            *trace << "]";
          }
          if (auto *IC = dyn_cast<ICmpInst>(&I)) {
            *trace << ",\"icmp_pred\":";
            emitJsonString(*trace, ICmpInst::getPredicateName(IC->getPredicate()));
          } else if (auto *FC = dyn_cast<FCmpInst>(&I)) {
            *trace << ",\"fcmp_pred\":";
            emitJsonString(*trace, FCmpInst::getPredicateName(FC->getPredicate()));
          }
          if (tx.present) {
            *trace << ",\"tx\":{";
            *trace << "\"kind\":";
            emitJsonString(*trace, tx.kind);
            *trace << ",\"which\":" << tx.operandIndex;
            *trace << "}";
          }
          *trace << "}\n";

          traceLine++;
          traceEmitted++;
          if (traceIndex) {
            emitTraceIndexRecord(*traceIndex, F.getName(), bbLabel, pp,
                                 opcode, defId, traceLine);
          }
          }
        }

        idx++;
        instCount++;
      }
    }

    if (cfg) {
      *cfg << "{";
      *cfg << "\"kind\":\"func_summary\",\"fn\":";
      emitJsonString(*cfg, F.getName());
      *cfg << ",\"inst_count\":" << instCount;
      *cfg << ",\"bb_count\":" << bbIndex.size();
      *cfg << ",\"tx_count\":" << txCount;
      *cfg << ",\"trace_emitted\":" << traceEmitted;
      *cfg << ",\"trace_truncated\":" << (traceTruncated ? "true" : "false");
      *cfg << ",\"trace_max_inst\":" << MaxInst;
      *cfg << "}\n";

      for (auto &BB : F) {
        const Instruction *T = BB.getTerminator();
        std::vector<std::string> succs;
        if (T) {
          for (unsigned i = 0; i < T->getNumSuccessors(); ++i) {
            const BasicBlock *Succ = T->getSuccessor(i);
            succs.push_back(bbLabels[Succ]);
          }
        }

        *cfg << "{";
        *cfg << "\"kind\":\"block\",\"fn\":";
        emitJsonString(*cfg, F.getName());
        *cfg << ",\"bb\":";
        emitJsonString(*cfg, bbLabels[&BB]);
        *cfg << ",\"succs\":";
        emitJsonStringArray(*cfg, succs);
        if (T) {
          *cfg << ",\"term_pp\":";
          emitJsonString(*cfg, termPP[&BB]);
          *cfg << ",\"term_op\":";
          emitJsonString(*cfg, T->getOpcodeName());

          if (auto *BI = dyn_cast<BranchInst>(T)) {
            if (BI->isConditional()) {
              *cfg << ",\"cond\":";
              emitJsonString(*cfg,
                             getValueId(BI->getCondition(),
                                        valueIds, nextValueId));
            }
          } else if (auto *SI = dyn_cast<SwitchInst>(T)) {
            *cfg << ",\"cond\":";
            emitJsonString(*cfg,
                           getValueId(SI->getCondition(),
                                      valueIds, nextValueId));
          } else if (auto *IB = dyn_cast<IndirectBrInst>(T)) {
            *cfg << ",\"target\":";
            emitJsonString(*cfg,
                           getValueId(IB->getAddress(),
                                      valueIds, nextValueId));
          }
        }
        *cfg << "}\n";

        if (!T) continue;
        if (auto *BI = dyn_cast<BranchInst>(T)) {
          if (BI->isConditional()) {
            std::string condId =
              getValueId(BI->getCondition(), valueIds, nextValueId);
            for (unsigned i = 0; i < BI->getNumSuccessors(); ++i) {
              *cfg << "{";
              *cfg << "\"kind\":\"edge\",\"fn\":";
              emitJsonString(*cfg, F.getName());
              *cfg << ",\"from\":";
              emitJsonString(*cfg, bbLabels[&BB]);
              *cfg << ",\"to\":";
              emitJsonString(*cfg, bbLabels[BI->getSuccessor(i)]);
              *cfg << ",\"term_pp\":";
              emitJsonString(*cfg, termPP[&BB]);
              *cfg << ",\"branch\":\"cond\",\"cond\":";
              emitJsonString(*cfg, condId);
              *cfg << ",\"sense\":";
              emitJsonString(*cfg, (i == 0) ? "true" : "false");
              *cfg << "}\n";
            }
          } else if (BI->getNumSuccessors() == 1) {
            *cfg << "{";
            *cfg << "\"kind\":\"edge\",\"fn\":";
            emitJsonString(*cfg, F.getName());
            *cfg << ",\"from\":";
            emitJsonString(*cfg, bbLabels[&BB]);
            *cfg << ",\"to\":";
            emitJsonString(*cfg, bbLabels[BI->getSuccessor(0)]);
            *cfg << ",\"term_pp\":";
            emitJsonString(*cfg, termPP[&BB]);
            *cfg << ",\"branch\":\"uncond\"";
            *cfg << "}\n";
          }
        } else if (auto *SI = dyn_cast<SwitchInst>(T)) {
          std::string condId =
            getValueId(SI->getCondition(), valueIds, nextValueId);
          for (auto &Case : SI->cases()) {
            *cfg << "{";
            *cfg << "\"kind\":\"edge\",\"fn\":";
            emitJsonString(*cfg, F.getName());
            *cfg << ",\"from\":";
            emitJsonString(*cfg, bbLabels[&BB]);
            *cfg << ",\"to\":";
            emitJsonString(*cfg, bbLabels[Case.getCaseSuccessor()]);
            *cfg << ",\"term_pp\":";
            emitJsonString(*cfg, termPP[&BB]);
            *cfg << ",\"branch\":\"switch\",\"cond\":";
            emitJsonString(*cfg, condId);
            *cfg << ",\"case\":";
            emitJsonString(*cfg,
                           getValueId(Case.getCaseValue(),
                                      valueIds, nextValueId));
            *cfg << "}\n";
          }
          if (const BasicBlock *Def = SI->getDefaultDest()) {
            *cfg << "{";
            *cfg << "\"kind\":\"edge\",\"fn\":";
            emitJsonString(*cfg, F.getName());
            *cfg << ",\"from\":";
            emitJsonString(*cfg, bbLabels[&BB]);
            *cfg << ",\"to\":";
            emitJsonString(*cfg, bbLabels[Def]);
            *cfg << ",\"term_pp\":";
            emitJsonString(*cfg, termPP[&BB]);
            *cfg << ",\"branch\":\"switch\",\"cond\":";
            emitJsonString(*cfg, condId);
            *cfg << ",\"default\":true";
            *cfg << "}\n";
          }
        } else if (auto *IB = dyn_cast<IndirectBrInst>(T)) {
          std::string targetId =
            getValueId(IB->getAddress(), valueIds, nextValueId);
          for (unsigned i = 0; i < IB->getNumSuccessors(); ++i) {
            *cfg << "{";
            *cfg << "\"kind\":\"edge\",\"fn\":";
            emitJsonString(*cfg, F.getName());
            *cfg << ",\"from\":";
            emitJsonString(*cfg, bbLabels[&BB]);
            *cfg << ",\"to\":";
            emitJsonString(*cfg, bbLabels[IB->getSuccessor(i)]);
            *cfg << ",\"term_pp\":";
            emitJsonString(*cfg, termPP[&BB]);
            *cfg << ",\"branch\":\"indirect\",\"target\":";
            emitJsonString(*cfg, targetId);
            *cfg << "}\n";
          }
        }
      }

      if (MaxPaths > 0) {
        unsigned emitted = 0;
        unsigned pathIdCounter = 0;
        bool truncated = false;
        bool cutoffDepth = false;
        bool cutoffLoop = false;
        unsigned constPrunedBr = 0;
        unsigned constPrunedSwitch = 0;
        unsigned constPrunedIndirect = 0;
        unsigned dfsCalls = 0;
        unsigned dfsLeaves = 0;
        unsigned dfsPruneMaxPaths = 0;
        unsigned dfsPruneMaxDepth = 0;
        unsigned dfsPruneLoop = 0;
        std::vector<const BasicBlock *> path;
        std::vector<Decision> decisions;
        std::vector<std::string> conds;
        std::vector<CondExpr> condExprs;
        StringMap<SmallVector<unsigned, 8>> ppToPaths;
        DenseMap<const BasicBlock *, unsigned> visitCount;

        std::function<void(const BasicBlock *)> dfs =
          [&](const BasicBlock *BB) {
            dfsCalls++;
            if (emitted >= MaxPaths) {
              truncated = true;
              dfsPruneMaxPaths++;
              return;
            }
            if (path.size() >= MaxPathDepth) {
              cutoffDepth = true;
              dfsPruneMaxDepth++;
              return;
            }

            unsigned count = visitCount[BB];
            unsigned maxVisits = MaxLoopIters + 1;
            if (count >= maxVisits) {
              cutoffLoop = true;
              dfsPruneLoop++;
              return;
            }
            visitCount[BB] = count + 1;
            path.push_back(BB);

            const Instruction *T = BB->getTerminator();
            unsigned succCount = T ? T->getNumSuccessors() : 0;
            if (!T || succCount == 0) {
              dfsLeaves++;
              unsigned pathId = pathIdCounter++;
              std::vector<std::string> ppSeq;
              if (IncludePpSeq || EmitPpCoverage) {
                for (const BasicBlock *PBB : path) {
                  auto it = bbPpSeq.find(PBB);
                  if (it == bbPpSeq.end()) continue;
                  const std::vector<std::string> &pps = it->second;
                  ppSeq.insert(ppSeq.end(), pps.begin(), pps.end());
                }
              }
              if (EmitPpCoverage) {
                DenseSet<StringRef> seen;
                for (const std::string &pp : ppSeq) {
                  StringRef key(pp);
                  if (!seen.insert(key).second) continue;
                  ppToPaths[key].push_back(pathId);
                }
              }

              *cfg << "{";
              *cfg << "\"kind\":\"path\",\"fn\":";
              emitJsonString(*cfg, F.getName());
              *cfg << ",\"path_id\":" << pathId;
              *cfg << ",\"bbs\":[";
              for (size_t i = 0; i < path.size(); ++i) {
                if (i) *cfg << ",";
                emitJsonString(*cfg, bbLabels[path[i]]);
              }
              *cfg << "],\"decisions\":[";
              for (size_t i = 0; i < decisions.size(); ++i) {
                if (i) *cfg << ",";
                emitDecision(*cfg, decisions[i]);
              }
              *cfg << "]";
              if (IncludePpSeq) {
                *cfg << ",\"pp_seq\":[";
                for (size_t i = 0; i < ppSeq.size(); ++i) {
                  if (i) *cfg << ",";
                  emitJsonString(*cfg, ppSeq[i]);
                }
                *cfg << "]";
              }
              if (emitCondStr) {
                *cfg << ",\"path_cond\":[";
                for (size_t i = 0; i < conds.size(); ++i) {
                  if (i) *cfg << ",";
                  emitJsonString(*cfg, conds[i]);
                }
                *cfg << "]";
              }
              if (emitCondJson) {
                *cfg << ",\"path_cond_json\":[";
                for (size_t i = 0; i < condExprs.size(); ++i) {
                  if (i) *cfg << ",";
                  emitCondExpr(*cfg, condExprs[i]);
                }
                *cfg << "]";
              }
              *cfg << "}\n";
              emitted++;
            } else {
              if (auto *BI = dyn_cast<BranchInst>(T)) {
                if (BI->isConditional()) {
                  std::string condId =
                    getValueId(BI->getCondition(), valueIds, nextValueId);
                  if (auto *CI = dyn_cast<ConstantInt>(BI->getCondition())) {
                    unsigned i = CI->isZero() ? 1 : 0;
                    constPrunedBr++;
                    Decision d;
                    d.pp = termPP[BB];
                    d.kind = "br";
                    d.cond = condId;
                    d.succ = bbLabels[BI->getSuccessor(i)];
                    d.sense = (i == 0) ? "true" : "false";
                    std::string condText =
                      condId + "==" +
                      std::string((i == 0) ? "const:i1:1" : "const:i1:0");
                    CondExpr condJson = makeCmp(
                      "==", condId,
                      (i == 0) ? "const:i1:1" : "const:i1:0");
                    decisions.push_back(d);
                    conds.push_back(condText);
                    condExprs.push_back(condJson);
                    dfs(BI->getSuccessor(i));
                    decisions.pop_back();
                    conds.pop_back();
                    condExprs.pop_back();
                  } else {
                    for (unsigned i = 0; i < BI->getNumSuccessors(); ++i) {
                      Decision d;
                      d.pp = termPP[BB];
                      d.kind = "br";
                      d.cond = condId;
                      d.succ = bbLabels[BI->getSuccessor(i)];
                      d.sense = (i == 0) ? "true" : "false";
                      std::string condText =
                        condId + "==" +
                        std::string((i == 0) ? "const:i1:1" : "const:i1:0");
                      CondExpr condJson = makeCmp(
                        "==", condId,
                        (i == 0) ? "const:i1:1" : "const:i1:0");
                      decisions.push_back(d);
                      conds.push_back(condText);
                      condExprs.push_back(condJson);
                      dfs(BI->getSuccessor(i));
                      decisions.pop_back();
                      conds.pop_back();
                      condExprs.pop_back();
                    }
                  }
                } else {
                  dfs(BI->getSuccessor(0));
                }
              } else if (auto *SI = dyn_cast<SwitchInst>(T)) {
                std::string condId =
                  getValueId(SI->getCondition(), valueIds, nextValueId);
                if (auto *CI = dyn_cast<ConstantInt>(SI->getCondition())) {
                  constPrunedSwitch++;
                  const BasicBlock *Dest = nullptr;
                  const ConstantInt *CaseVal = nullptr;
                  for (auto &Case : SI->cases()) {
                    if (Case.getCaseValue()->getValue() == CI->getValue()) {
                      Dest = Case.getCaseSuccessor();
                      CaseVal = Case.getCaseValue();
                      break;
                    }
                  }
                  if (Dest) {
                    Decision d;
                    d.pp = termPP[BB];
                    d.kind = "switch";
                    d.cond = condId;
                    d.succ = bbLabels[Dest];
                    d.caseValue =
                      getValueId(CaseVal, valueIds, nextValueId);
                    std::string condText = condId + "==" + d.caseValue;
                    CondExpr condJson = makeCmp("==", condId, d.caseValue);
                    decisions.push_back(d);
                    conds.push_back(condText);
                    condExprs.push_back(condJson);
                    dfs(Dest);
                    decisions.pop_back();
                    conds.pop_back();
                    condExprs.pop_back();
                  } else if (const BasicBlock *Def = SI->getDefaultDest()) {
                    Decision d;
                    d.pp = termPP[BB];
                    d.kind = "switch";
                    d.cond = condId;
                    d.succ = bbLabels[Def];
                    d.isDefault = true;
                    std::string condText =
                      buildSwitchDefaultCond(*SI, condId, valueIds, nextValueId);
                    std::vector<CondExpr> terms;
                    for (auto &Case : SI->cases()) {
                      std::string caseVal =
                        getValueId(Case.getCaseValue(), valueIds, nextValueId);
                      terms.push_back(makeCmp("!=", condId, caseVal));
                    }
                    CondExpr condJson;
                    if (terms.empty()) {
                      condJson = makeCmp("!=", condId, "<any>");
                    } else if (terms.size() == 1) {
                      condJson = terms[0];
                    } else {
                      condJson = makeAnd(std::move(terms));
                    }
                    decisions.push_back(d);
                    conds.push_back(condText);
                    condExprs.push_back(condJson);
                    dfs(Def);
                    decisions.pop_back();
                    conds.pop_back();
                    condExprs.pop_back();
                  }
                } else {
                  for (auto &Case : SI->cases()) {
                    Decision d;
                    d.pp = termPP[BB];
                    d.kind = "switch";
                    d.cond = condId;
                    d.succ = bbLabels[Case.getCaseSuccessor()];
                    d.caseValue =
                      getValueId(Case.getCaseValue(), valueIds, nextValueId);
                    std::string condText = condId + "==" + d.caseValue;
                    CondExpr condJson = makeCmp("==", condId, d.caseValue);
                    decisions.push_back(d);
                    conds.push_back(condText);
                    condExprs.push_back(condJson);
                    dfs(Case.getCaseSuccessor());
                    decisions.pop_back();
                    conds.pop_back();
                    condExprs.pop_back();
                  }
                  if (const BasicBlock *Def = SI->getDefaultDest()) {
                    Decision d;
                    d.pp = termPP[BB];
                    d.kind = "switch";
                    d.cond = condId;
                    d.succ = bbLabels[Def];
                    d.isDefault = true;
                    std::string condText =
                      buildSwitchDefaultCond(*SI, condId, valueIds, nextValueId);
                    std::vector<CondExpr> terms;
                    for (auto &Case : SI->cases()) {
                      std::string caseVal =
                        getValueId(Case.getCaseValue(), valueIds, nextValueId);
                      terms.push_back(makeCmp("!=", condId, caseVal));
                    }
                    CondExpr condJson;
                    if (terms.empty()) {
                      condJson = makeCmp("!=", condId, "<any>");
                    } else if (terms.size() == 1) {
                      condJson = terms[0];
                    } else {
                      condJson = makeAnd(std::move(terms));
                    }
                    decisions.push_back(d);
                    conds.push_back(condText);
                    condExprs.push_back(condJson);
                    dfs(Def);
                    decisions.pop_back();
                    conds.pop_back();
                    condExprs.pop_back();
                  }
                }
              } else if (auto *IB = dyn_cast<IndirectBrInst>(T)) {
                std::string targetId =
                  getValueId(IB->getAddress(), valueIds, nextValueId);
                if (auto *BA = dyn_cast<BlockAddress>(IB->getAddress())) {
                  constPrunedIndirect++;
                  const BasicBlock *Dest = BA->getBasicBlock();
                  Decision d;
                  d.pp = termPP[BB];
                  d.kind = "indirect";
                  d.target = targetId;
                  d.succ = bbLabels[Dest];
                  std::string condText =
                    targetId + "==label:" + d.succ;
                  CondExpr condJson =
                    makeCmp("==", targetId, "label:" + d.succ);
                  decisions.push_back(d);
                  conds.push_back(condText);
                  condExprs.push_back(condJson);
                  dfs(Dest);
                  decisions.pop_back();
                  conds.pop_back();
                  condExprs.pop_back();
                } else {
                  for (unsigned i = 0; i < IB->getNumSuccessors(); ++i) {
                    Decision d;
                    d.pp = termPP[BB];
                    d.kind = "indirect";
                    d.target = targetId;
                    d.succ = bbLabels[IB->getSuccessor(i)];
                    std::string condText =
                      targetId + "==label:" + d.succ;
                    CondExpr condJson =
                      makeCmp("==", targetId, "label:" + d.succ);
                    decisions.push_back(d);
                    conds.push_back(condText);
                    condExprs.push_back(condJson);
                    dfs(IB->getSuccessor(i));
                    decisions.pop_back();
                    conds.pop_back();
                    condExprs.pop_back();
                  }
                }
              } else {
                for (unsigned i = 0; i < succCount; ++i) {
                  dfs(T->getSuccessor(i));
                }
              }
            }

            path.pop_back();
            visitCount[BB] = count;
          };

        dfs(&F.getEntryBlock());
        if (EmitPpCoverage) {
          for (auto &entry : ppToPaths) {
            StringRef pp = entry.getKey();
            SmallVector<unsigned, 8> &ids = entry.getValue();
            *cfg << "{";
            *cfg << "\"kind\":\"pp_coverage\",\"fn\":";
            emitJsonString(*cfg, F.getName());
            *cfg << ",\"pp\":";
            emitJsonString(*cfg, pp);
            *cfg << ",\"path_count\":" << ids.size();
            *cfg << ",\"path_ids\":[";
            unsigned limit = MaxPpPathIds;
            for (unsigned i = 0; i < ids.size() && i < limit; ++i) {
              if (i) *cfg << ",";
              *cfg << ids[i];
            }
            *cfg << "]";
            if (ids.size() > limit) {
              *cfg << ",\"truncated\":true";
            }
            *cfg << "}\n";
          }
        }
        *cfg << "{";
        *cfg << "\"kind\":\"path_summary\",\"fn\":";
        emitJsonString(*cfg, F.getName());
        *cfg << ",\"paths_emitted\":" << emitted;
        *cfg << ",\"truncated\":" << (truncated ? "true" : "false");
        *cfg << ",\"max_paths\":" << MaxPaths;
        *cfg << ",\"max_depth\":" << MaxPathDepth;
        *cfg << ",\"max_loop_iters\":" << MaxLoopIters;
        *cfg << ",\"cutoff_depth\":" << (cutoffDepth ? "true" : "false");
        *cfg << ",\"cutoff_loop\":" << (cutoffLoop ? "true" : "false");
        *cfg << ",\"const_pruned_br\":" << constPrunedBr;
        *cfg << ",\"const_pruned_switch\":" << constPrunedSwitch;
        *cfg << ",\"const_pruned_indirect\":" << constPrunedIndirect;
        *cfg << ",\"dfs_calls\":" << dfsCalls;
        *cfg << ",\"dfs_leaves\":" << dfsLeaves;
        *cfg << ",\"dfs_prune_max_paths\":" << dfsPruneMaxPaths;
        *cfg << ",\"dfs_prune_max_depth\":" << dfsPruneMaxDepth;
        *cfg << ",\"dfs_prune_loop\":" << dfsPruneLoop;
        *cfg << "}\n";
      } else {
        *cfg << "{";
        *cfg << "\"kind\":\"path_summary\",\"fn\":";
        emitJsonString(*cfg, F.getName());
        *cfg << ",\"paths_emitted\":0";
        *cfg << ",\"disabled\":true";
        *cfg << ",\"max_paths\":" << MaxPaths;
        *cfg << ",\"max_depth\":" << MaxPathDepth;
        *cfg << ",\"max_loop_iters\":" << MaxLoopIters;
        *cfg << "}\n";
      }
    }

    return PreservedAnalyses::all();
  }
};

} // namespace

// Pass registration for `opt -load-pass-plugin ... -passes=public-data`
extern "C" LLVM_ATTRIBUTE_WEAK PassPluginLibraryInfo llvmGetPassPluginInfo() {
  return {
    LLVM_PLUGIN_API_VERSION, "PublicDataPass", LLVM_VERSION_STRING,
    [](PassBuilder &PB) {
      PB.registerPipelineParsingCallback(
        [](StringRef Name, FunctionPassManager &FPM,
           ArrayRef<PassBuilder::PipelineElement>) {
          if (Name == "public-data") {
            FPM.addPass(PublicDataPass());
            return true;
          }
          return false;
        }
      );
    }
  };
}
