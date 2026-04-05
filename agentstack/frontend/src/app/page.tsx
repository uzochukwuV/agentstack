import Navbar from "@/components/layout/Navbar";
import { Bot, Shield, Zap, Activity } from "lucide-react";
import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen bg-background pt-14">
      <Navbar />
      
      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 scanline pointer-events-none opacity-50" />
        {/* Grid background */}
        <div className="absolute inset-0 opacity-[0.03]" style={{
          backgroundImage: "linear-gradient(hsl(var(--primary)) 1px, transparent 1px), linear-gradient(90deg, hsl(var(--primary)) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
        }} />
        <div className="max-w-5xl mx-auto px-6 py-20 md:py-28 text-center relative">
          <div className="animate-in fade-in slide-in-from-bottom-8 duration-700">
            <div className="inline-flex items-center gap-2 px-4 py-1.5 rounded-full border border-primary/30 bg-primary/5 text-primary text-xs font-mono mb-6">
              <Bot className="w-3.5 h-3.5" /> SterlingStack DeFAI Agent
            </div>
            <h1 className="text-5xl md:text-7xl font-bold text-foreground mb-6 leading-tight tracking-tight">
              Autonomous Trading<br />
              <span className="text-primary text-glow-green">On Arbitrum</span>
            </h1>
            <p className="text-lg md:text-xl text-muted-foreground max-w-2xl mx-auto mb-10 leading-relaxed">
              Subscribe to deploy an autonomous AI agent to manage your DeFi portfolio.
              Your funds stay in your wallet via EIP-7702 delegation.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Link 
                href="/dashboard"
                className="px-8 py-3 bg-primary text-primary-foreground font-semibold rounded-lg hover:bg-primary/90 transition-colors flex items-center gap-2"
              >
                <Zap className="w-4 h-4" /> Enable Agent
              </Link>
              <Link 
                href="/chat"
                className="px-8 py-3 bg-card border border-border text-foreground font-semibold rounded-lg hover:border-primary/50 transition-colors flex items-center gap-2"
              >
                <Bot className="w-4 h-4" /> Talk to Agent
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* How it Works */}
      <section className="max-w-5xl mx-auto px-6 pb-16">
        <div className="bg-card border border-border rounded-xl p-8 mb-16 animate-in fade-in duration-1000 delay-300 fill-mode-both">
          <h2 className="text-lg font-semibold text-foreground mb-6 text-center">How It Works</h2>
          <div className="grid md:grid-cols-3 gap-8">
            {[
              { step: "01", title: "Connect Wallet", desc: "Sign in with Ethereum and authorize the agent using EIP-7702. Funds never leave your control.", icon: Shield },
              { step: "02", title: "Set Goals", desc: "Chat with the agent to set your yield targets, risk tolerance, and preferred protocols.", icon: Bot },
              { step: "03", title: "Autonomous Execution", desc: "The agent polls markets every 5 minutes and executes trades on your behalf to optimize yield.", icon: Activity },
            ].map((item) => (
              <div key={item.step} className="text-center">
                <div className="text-3xl font-bold text-primary/20 font-mono mb-3">{item.step}</div>
                <div className="w-10 h-10 rounded-lg bg-primary/10 flex items-center justify-center mx-auto mb-3">
                  <item.icon className="w-5 h-5 text-primary" />
                </div>
                <h3 className="text-sm font-semibold text-foreground mb-2">{item.title}</h3>
                <p className="text-xs text-muted-foreground leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <footer className="border-t border-border pt-8 text-center">
          <p className="text-xs text-muted-foreground font-mono">
            Powered by <span className="text-primary">SterlingStack</span> — DeFAI on Arbitrum
          </p>
        </footer>
      </section>
    </div>
  );
}