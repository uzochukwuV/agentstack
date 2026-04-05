"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "framer-motion";
import { Bot, LineChart, Wallet, Menu, X, Activity } from "lucide-react";

const Navbar = () => {
  const pathname = usePathname();
  const [mobileOpen, setMobileOpen] = useState(false);

  const links = [
    { to: "/", label: "Dashboard", icon: Activity },
    { to: "/chat", label: "Agent Chat", icon: Bot },
  ];

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-background/80 backdrop-blur-xl border-b border-border">
      <div className="max-w-6xl mx-auto px-4 md:px-6 h-14 flex items-center justify-between">
        <Link href="/" className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-md bg-primary/10 flex items-center justify-center">
            <LineChart className="w-4 h-4 text-primary" />
          </div>
          <span className="font-bold text-foreground text-lg">
            Sterling<span className="text-primary">Stack</span>
          </span>
        </Link>

        {/* Desktop */}
        <div className="hidden md:flex items-center gap-0.5">
          {links.map((link) => {
            const isActive = pathname === link.to;
            return (
              <Link
                key={link.to}
                href={link.to}
                className={`relative px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                  isActive ? "text-primary" : "text-muted-foreground hover:text-foreground"
                }`}
              >
                {isActive && (
                  <motion.div
                    layoutId="navbar-active"
                    className="absolute inset-0 bg-primary/10 rounded-md"
                    transition={{ type: "spring", duration: 0.4 }}
                  />
                )}
                <span className="relative flex items-center gap-1.5">
                  <link.icon className="w-4 h-4" />
                  {link.label}
                </span>
              </Link>
            );
          })}
          
          {/* Wallet Connect Button Placeholder */}
          <button className="ml-4 px-4 py-1.5 text-sm font-medium bg-primary text-primary-foreground rounded-md flex items-center gap-2 hover:bg-primary/90 transition-colors">
            <Wallet className="w-4 h-4" />
            Connect Wallet
          </button>
        </div>

        {/* Mobile toggle */}
        <button className="md:hidden text-muted-foreground" onClick={() => setMobileOpen(!mobileOpen)}>
          {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="md:hidden bg-background border-b border-border px-4 pb-4"
        >
          {links.map((link) => {
            const isActive = pathname === link.to;
            return (
              <Link
                key={link.to}
                href={link.to}
                onClick={() => setMobileOpen(false)}
                className={`flex items-center gap-2 px-3 py-2.5 text-sm rounded-md mb-1 ${
                  isActive ? "text-primary bg-primary/10" : "text-muted-foreground"
                }`}
              >
                <link.icon className="w-4 h-4" />
                {link.label}
              </Link>
            );
          })}
          <button className="w-full mt-2 px-3 py-2.5 text-sm font-medium bg-primary text-primary-foreground rounded-md flex items-center gap-2 justify-center">
            <Wallet className="w-4 h-4" />
            Connect Wallet
          </button>
        </motion.div>
      )}
    </nav>
  );
};

export default Navbar;