"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Bot, Send, User } from "lucide-react";
import Navbar from "@/components/layout/Navbar";

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
};

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "1",
      role: "assistant",
      content: "Hello! I'm your SterlingStack Agent. Tell me your yield targets or risk preferences, and I'll update your portfolio strategy.",
    },
  ]);
  const [input, setInput] = useState("");

  const handleSend = () => {
    if (!input.trim()) return;
    
    const newMsg: Message = { id: Date.now().toString(), role: "user", content: input };
    setMessages((prev) => [...prev, newMsg]);
    setInput("");

    // Simulate agent response
    setTimeout(() => {
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: "I've noted your preference. I will adjust the strategy accordingly during my next 5-minute polling cycle.",
        },
      ]);
    }, 1000);
  };

  return (
    <div className="min-h-screen bg-background pt-14 flex flex-col">
      <Navbar />
      
      <div className="flex-1 max-w-4xl w-full mx-auto p-4 md:p-6 flex flex-col h-[calc(100vh-3.5rem)]">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-foreground">Agent Chat</h1>
          <p className="text-sm text-muted-foreground">Configure your autonomous trading agent</p>
        </div>

        <div className="flex-1 bg-card border border-border rounded-xl flex flex-col overflow-hidden shadow-lg">
          <ScrollArea className="flex-1 p-4">
            <div className="space-y-6">
              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : "flex-row"}`}
                >
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
                      msg.role === "user" ? "bg-primary text-primary-foreground" : "bg-secondary text-secondary-foreground"
                    }`}
                  >
                    {msg.role === "user" ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
                  </div>
                  <div
                    className={`px-4 py-3 rounded-2xl max-w-[80%] text-sm leading-relaxed ${
                      msg.role === "user"
                        ? "bg-primary text-primary-foreground rounded-tr-sm"
                        : "bg-secondary text-secondary-foreground rounded-tl-sm"
                    }`}
                  >
                    {msg.content}
                  </div>
                </div>
              ))}
            </div>
          </ScrollArea>

          <div className="p-4 bg-card border-t border-border">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSend();
              }}
              className="flex gap-3"
            >
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Message your agent..."
                className="flex-1 bg-background border-border focus-visible:ring-primary"
              />
              <Button type="submit" disabled={!input.trim()} className="bg-primary text-primary-foreground hover:bg-primary/90 px-4">
                <Send className="w-4 h-4" />
              </Button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}