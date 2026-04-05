"use client";

import Navbar from "@/components/layout/Navbar";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Activity, ArrowUpRight, CheckCircle2, ShieldAlert, Zap } from "lucide-react";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip } from "recharts";

const data = [
  { time: "00:00", value: 1000 },
  { time: "04:00", value: 1050 },
  { time: "08:00", value: 1020 },
  { time: "12:00", value: 1100 },
  { time: "16:00", value: 1150 },
  { time: "20:00", value: 1120 },
  { time: "24:00", value: 1200 },
];

export default function DashboardPage() {
  return (
    <div className="min-h-screen bg-background pt-14">
      <Navbar />
      
      <div className="max-w-6xl mx-auto p-4 md:p-6 space-y-6">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-foreground">Dashboard</h1>
            <p className="text-muted-foreground mt-1">Monitor your autonomous agent&apos;s performance</p>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-primary/10 border border-primary/20 text-primary text-sm font-medium">
            <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
            Agent Active
          </div>
        </div>

        {/* Top Stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card className="bg-card border-border">
            <CardHeader className="pb-2">
              <CardDescription>Total Portfolio Value</CardDescription>
              <CardTitle className="text-3xl text-glow-green text-primary">$1,200.00</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex items-center text-sm text-muted-foreground">
                <ArrowUpRight className="w-4 h-4 mr-1 text-primary" />
                <span className="text-primary font-medium mr-2">+12.5%</span>
                this week
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card border-border">
            <CardHeader className="pb-2">
              <CardDescription>Capital Utilisation</CardDescription>
              <CardTitle className="text-3xl">65%</CardTitle>
            </CardHeader>
            <CardContent>
              <Progress value={65} className="h-2 bg-secondary" />
              <p className="text-xs text-muted-foreground mt-2 flex justify-between">
                <span>Optimal Zone</span>
                <span>$780 Deployed</span>
              </p>
            </CardContent>
          </Card>

          <Card className="bg-card border-border">
            <CardHeader className="pb-2">
              <CardDescription>Last Agent Action</CardDescription>
              <CardTitle className="text-lg flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 text-primary" />
                Supplied to Aave V3
              </CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">10.0 USDC at 4.2% APY</p>
              <p className="text-xs text-muted-foreground mt-1">2 hours ago</p>
            </CardContent>
          </Card>
        </div>

        {/* Chart & Activity */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <Card className="bg-card border-border lg:col-span-2">
            <CardHeader>
              <CardTitle>Performance History</CardTitle>
              <CardDescription>Portfolio value over the last 24 hours</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-[300px] w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.3} />
                        <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <XAxis 
                      dataKey="time" 
                      stroke="hsl(var(--muted-foreground))" 
                      fontSize={12} 
                      tickLine={false}
                      axisLine={false}
                    />
                    <YAxis 
                      stroke="hsl(var(--muted-foreground))" 
                      fontSize={12}
                      tickLine={false}
                      axisLine={false}
                      tickFormatter={(value) => `$${value}`}
                    />
                    <Tooltip 
                      contentStyle={{ backgroundColor: "hsl(var(--card))", borderColor: "hsl(var(--border))" }}
                      itemStyle={{ color: "hsl(var(--foreground))" }}
                    />
                    <Area 
                      type="monotone" 
                      dataKey="value" 
                      stroke="hsl(var(--primary))" 
                      fillOpacity={1} 
                      fill="url(#colorValue)" 
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-card border-border">
            <CardHeader>
              <CardTitle>Recent Activity</CardTitle>
              <CardDescription>Latest agent transactions</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-6">
                {[
                  { title: "Supplied USDC", protocol: "Aave V3", time: "2h ago", amount: "$10.00", icon: Zap, color: "text-primary" },
                  { title: "Swapped to WETH", protocol: "Uniswap V3", time: "5h ago", amount: "$5.00", icon: Activity, color: "text-neon-purple" },
                  { title: "Health Check", protocol: "System", time: "12h ago", amount: "OK", icon: ShieldAlert, color: "text-muted-foreground" },
                ].map((act, i) => (
                  <div key={i} className="flex items-center gap-4">
                    <div className={`w-8 h-8 rounded-full bg-secondary flex items-center justify-center shrink-0 ${act.color}`}>
                      <act.icon className="w-4 h-4" />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-foreground truncate">{act.title}</p>
                      <p className="text-xs text-muted-foreground">{act.protocol}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-sm font-medium text-foreground">{act.amount}</p>
                      <p className="text-xs text-muted-foreground">{act.time}</p>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}