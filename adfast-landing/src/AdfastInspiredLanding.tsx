import { useState } from 'react';
import {
  Activity, BarChart3, Check, ChevronDown, DatabaseZap,
  ShieldCheck, Star,
  Search, Link2, DollarSign, PenTool, Hourglass, XCircle, Zap,
  Truck, ShieldAlert, Puzzle, LayoutDashboard
} from 'lucide-react';

const CLIENT_PORTAL_URL = 'https://client.buykori.app';

const features = [
  { title: 'Track Real Engagement', desc: 'Capture PageView, ViewContent, AddToCart, checkout intent and purchases with cleaner attribution.', icon: BarChart3, stat: '+24.8%', statLabel: 'Event Recovery' },
  { title: 'Signal Health Doctor', desc: 'Find missing product IDs, weak match quality and platform delivery warnings before campaigns waste budget.', icon: ShieldCheck, stat: '94/100', statLabel: 'Health Score' },
  { title: 'Campaign Monitoring', desc: 'See Meta, TikTok and GA4 event delivery status from one lightweight dashboard.', icon: Activity, stat: '3x', statLabel: 'Faster Debugging' },
];

const freeTools = [
  { title: 'Tracking Checker', desc: 'Scan a website and show whether Meta, TikTok, GA4 and server events are active.', icon: Search, color: 'text-indigo-600 bg-indigo-50 border-indigo-100' },
  { title: 'Event Tester', desc: 'Send test PageView, ViewContent, AddToCart, Checkout and Purchase events.', icon: Zap, color: 'text-amber-600 bg-amber-50 border-amber-100' },
  { title: 'UTM Builder', desc: 'Create clean campaign links for Facebook, TikTok and Google ads.', icon: Link2, color: 'text-emerald-600 bg-emerald-50 border-emerald-100' },
  { title: 'Ads Profit Calculator', desc: 'Estimate ROAS, CPA and profit before increasing campaign budget.', icon: DollarSign, color: 'text-rose-600 bg-rose-50 border-rose-100' },
  { title: 'Content ID Fix', desc: 'Reduce missing content warnings by checking product IDs and catalog signals.', icon: PenTool, color: 'text-violet-600 bg-violet-50 border-violet-100' },
  { title: 'Deferred Purchase', desc: 'Confirm COD and delayed orders before sending final purchase signals.', icon: Hourglass, color: 'text-sky-600 bg-sky-50 border-sky-100' },
];

const plans = [
  { name: 'Free Plan', price: '$0', note: 'For testing one WooCommerce store.', points: ['One store setup', 'Basic server events', 'Campaign URL builder'] },
  { name: 'Pro Plan', price: '$19', note: 'For growing stores and marketers.', points: ['Meta, TikTok and GA4', 'Signal Health Doctor', 'Deferred Purchase control', 'Priority support'] },
  { name: 'Enterprise Plan', price: 'Custom', note: 'For agencies and multi-store teams.', points: ['Multi-client dashboard', 'Custom domains', 'Advanced event quality'] },
];

const comparison = [
  { area: 'Setup', buykori: 'Plugin, API key and guided platform settings.', manual: 'Manual tags, server config and custom debugging.' },
  { area: 'Event quality', buykori: 'Signal doctor, content ID checks and enrichment flow.', manual: 'Depends on developer implementation and ongoing review.' },
  { area: 'Purchase control', buykori: 'Deferred purchase and COD confirmation workflow.', manual: 'Usually needs custom logic per store.' },
  { area: 'Monitoring', buykori: 'Dashboard, logs, platform status and campaign tools.', manual: 'Separate tools and manual platform checks.' },
];

const testimonials = [
  { quote: "The dashboard makes tracking issues easier to explain before campaigns waste budget.", author: "Agency Operator", role: "Meta and TikTok ads" },
  { quote: "Deferred purchase tracking is exactly what COD stores need before sending final purchase data.", author: "WooCommerce Owner", role: "Bangladesh ecommerce" },
  { quote: "Campaign URL Builder plus server events makes source reporting much cleaner across channels.", author: "Performance Marketer", role: "Multi-platform campaigns" }
];

const faqs = [
  ['What is Buykori AdSync?', 'A server-side tracking platform that sends cleaner WooCommerce events to Meta CAPI, TikTok Events API and GA4.'],
  ['Does it support one-page landing pages?', 'Yes. One-page mode can wait for real checkout intent before sending InitiateCheckout.'],
  ['Can I use only TikTok or only Meta?', 'Yes. Platform toggles can control which destination receives events for each store.'],
  ['What data improves event match quality?', 'Content IDs, value, currency, click IDs, user agent, IP and hashed customer fields help platforms match events better.'],
];

function Logo() {
  return (
    <div className="flex items-center gap-2 font-bold text-slate-900 text-lg tracking-tight">
      <span className="flex items-center justify-center w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-lg shadow-indigo-500/30">
        <DatabaseZap size={18} />
      </span>
      <span>Buykori <span className="text-indigo-600">AdSync</span></span>
    </div>
  );
}

function DashboardPreview() {
  return (
    <div className="relative w-full max-w-[650px] mx-auto z-10">
      <div className="glass rounded-2xl animate-float-card overflow-hidden border border-slate-200/60 shadow-[0_20px_60px_-15px_rgba(79,70,229,0.15)] bg-white/70 backdrop-blur-xl">
        {/* Browser Top Bar */}
        <div className="flex items-center gap-2 h-12 px-4 border-b border-slate-200/50 bg-white/40">
          <div className="w-3 h-3 rounded-full bg-rose-400" />
          <div className="w-3 h-3 rounded-full bg-amber-400" />
          <div className="w-3 h-3 rounded-full bg-emerald-400" />
          <div className="ml-auto w-32 h-6 rounded-full bg-slate-200/50" />
        </div>
        
        {/* Dashboard Content */}
        <div className="flex">
          <aside className="hidden sm:block w-40 p-4 border-r border-slate-100 bg-slate-50/50 min-h-[400px]">
            <div className="mb-6 scale-90 origin-left"><Logo /></div>
            {['Dashboard', 'Events', 'Quality', 'Reports', 'Settings'].map((item, index) => (
              <p 
                key={item}
                className={`px-3 py-2 rounded-lg text-xs font-semibold mb-2 transition-colors ${
                  index === 0 
                    ? 'bg-gradient-to-r from-indigo-500 to-violet-600 text-white shadow-md shadow-indigo-500/20' 
                    : 'text-slate-600 hover:bg-slate-200/50'
                }`}
              >
                {item}
              </p>
            ))}
          </aside>
          
          <main className="flex-1 p-5 bg-white/40">
            <div className="flex items-center justify-between mb-5">
              <div>
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Overview</span>
                <h3 className="text-lg font-bold text-slate-800 leading-tight">Campaign Dashboard</h3>
              </div>
              <span className="px-3 py-1 rounded-full border border-slate-200 text-xs font-semibold text-slate-600 bg-white shadow-sm">Last 24h</span>
            </div>
            
            <div className="grid grid-cols-3 gap-3 mb-4">
              {[
                ['Events', '16,928', '+12.6%'],
                ['Match Rate', '92.7%', '+6.3%'],
                ['Revenue', '$8.7K', '+18.1%'],
              ].map(([label, value, trend]) => (
                <div key={label} className="p-3 bg-white rounded-xl border border-slate-100 shadow-sm">
                  <span className="block text-[10px] font-bold text-slate-400 uppercase">{label}</span>
                  <span className="block text-xl font-extrabold text-slate-800 mt-1">{value}</span>
                  <span className="block text-[10px] font-bold text-emerald-500 mt-0.5">{trend}</span>
                </div>
              ))}
            </div>
            
            <div className="flex items-end gap-2 h-24 p-4 rounded-xl bg-slate-50 border border-slate-100 mb-4">
              {[38, 56, 42, 76, 68, 92, 64, 84, 58, 74].map((height, index) => (
                <div 
                  key={index} 
                  className="flex-1 rounded-t-sm bg-gradient-to-t from-indigo-500 to-violet-400 opacity-80"
                  style={{ height: `${height}%` }}
                />
              ))}
            </div>
            
            <div className="grid grid-cols-2 gap-3">
              <div className="flex items-center gap-3 p-3 bg-white border border-slate-100 rounded-xl shadow-sm">
                <div className="flex items-center justify-center w-12 h-12 rounded-full border-4 border-emerald-400 border-r-emerald-100 text-lg font-extrabold text-slate-800">
                  94
                </div>
                <div>
                  <span className="block text-xs font-bold text-slate-800">Signal Health</span>
                  <span className="block text-[10px] text-slate-500 mt-0.5">Excellent quality</span>
                </div>
              </div>
              <div className="p-3 bg-white border border-slate-100 rounded-xl shadow-sm">
                <span className="block text-[10px] font-bold text-slate-400 uppercase mb-2">Top Events</span>
                <div className="space-y-1">
                  <div className="flex justify-between text-[11px]"><span className="text-slate-600">PageView</span><span className="font-bold text-slate-800">9,842</span></div>
                  <div className="flex justify-between text-[11px]"><span className="text-slate-600">ViewContent</span><span className="font-bold text-slate-800">6,215</span></div>
                  <div className="flex justify-between text-[11px]"><span className="text-slate-600">Purchase</span><span className="font-bold text-slate-800">1,010</span></div>
                </div>
              </div>
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}

function DataFlowBackground() {
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none">
      <div className="absolute top-[10%] left-[15%] w-3 h-3 bg-indigo-400/40 rounded-full animate-pulse"></div>
      <div className="absolute top-[25%] left-[5%] w-2 h-2 bg-emerald-400/50 rounded-full animate-ping" style={{ animationDuration: '3s' }}></div>
      <div className="absolute top-[40%] right-[20%] w-4 h-4 bg-violet-400/30 rounded-full animate-pulse" style={{ animationDelay: '1s' }}></div>
      <div className="absolute bottom-[20%] left-[25%] w-2 h-2 bg-indigo-500/40 rounded-full animate-ping" style={{ animationDuration: '2s' }}></div>
      <div className="absolute bottom-[10%] right-[15%] w-3 h-3 bg-emerald-400/40 rounded-full animate-pulse" style={{ animationDelay: '0.5s' }}></div>
      <svg className="absolute inset-0 w-full h-full opacity-30" xmlns="http://www.w3.org/2000/svg">
        <defs>
          <linearGradient id="flow1" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="rgba(99,102,241,0)" />
            <stop offset="50%" stopColor="rgba(99,102,241,0.5)" />
            <stop offset="100%" stopColor="rgba(99,102,241,0)" />
          </linearGradient>
          <linearGradient id="flow2" x1="100%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="rgba(16,185,129,0)" />
            <stop offset="50%" stopColor="rgba(16,185,129,0.5)" />
            <stop offset="100%" stopColor="rgba(16,185,129,0)" />
          </linearGradient>
        </defs>
        <path className="data-line-1" d="M -100,100 C 200,300 400,0 800,200 S 1200,-100 1600,100" fill="none" stroke="url(#flow1)" strokeWidth="2" />
        <path className="data-line-2" d="M -100,400 C 300,100 600,500 900,200 S 1300,600 1600,300" fill="none" stroke="url(#flow2)" strokeWidth="1.5" />
      </svg>
    </div>
  );
}

export default function AdfastInspiredLanding() {
  const [openFaq, setOpenFaq] = useState<number | null>(0);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <div className="min-h-screen bg-[#F8FAFC] text-slate-900 font-sans selection:bg-indigo-500/30 selection:text-indigo-900 overflow-x-hidden">
      
      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 glass border-b border-slate-200/50 bg-white/70 backdrop-blur-xl">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-[68px]">
            <Logo />
            
            {/* Desktop Nav */}
            <div className="hidden md:flex items-center space-x-8">
              {['Features', 'Product', 'Solution', 'Pricing', 'FAQ'].map(item => (
                <a key={item} href={`#${item.toLowerCase()}`} className="text-[13px] font-bold text-slate-500 hover:text-slate-900 transition-colors">
                  {item}
                </a>
              ))}
            </div>

            <div className="hidden md:flex items-center space-x-4">
              <a href={CLIENT_PORTAL_URL} className="text-[13px] font-bold text-slate-500 hover:text-slate-900 transition-colors">Sign in</a>
              <a href={CLIENT_PORTAL_URL} className="inline-flex items-center justify-center px-5 py-2 text-[13px] font-bold text-white bg-gradient-to-r from-indigo-500 to-violet-600 hover:-translate-y-0.5 rounded-full transition-all shadow-[0_4px_16px_rgba(79,70,229,0.25)]">
                Get Started &rarr;
              </a>
            </div>

            {/* Mobile Menu Button */}
            <button 
              className="md:hidden p-2 text-slate-600 hover:text-indigo-600"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            >
              <div className="w-6 flex flex-col items-end gap-1.5">
                <span className={`block h-0.5 w-full bg-current transition-transform ${mobileMenuOpen ? 'rotate-45 translate-y-2' : ''}`}></span>
                <span className={`block h-0.5 w-4/5 bg-current transition-opacity ${mobileMenuOpen ? 'opacity-0' : ''}`}></span>
                <span className={`block h-0.5 w-full bg-current transition-transform ${mobileMenuOpen ? '-rotate-45 -translate-y-2' : ''}`}></span>
              </div>
            </button>
          </div>
        </div>

        {/* Mobile Nav */}
        {mobileMenuOpen && (
          <div className="md:hidden absolute top-full left-0 w-full border-t border-slate-100 py-6 px-6 flex flex-col space-y-4 shadow-xl bg-white/95 backdrop-blur-xl">
            {['Features', 'Product', 'Solution', 'Pricing', 'FAQ'].map(item => (
              <a key={item} href={`#${item.toLowerCase()}`} className="text-base font-bold text-slate-800 pb-2 border-b border-slate-100" onClick={() => setMobileMenuOpen(false)}>
                {item}
              </a>
            ))}
            <div className="pt-4 flex flex-col gap-3">
              <a href={CLIENT_PORTAL_URL} className="flex justify-center items-center py-3 rounded-full bg-slate-100 text-slate-800 font-bold text-sm">Sign in</a>
              <a href={CLIENT_PORTAL_URL} className="flex justify-center items-center py-3 rounded-full bg-indigo-600 text-white font-bold text-sm">Get Started &rarr;</a>
            </div>
          </div>
        )}
      </nav>

      {/* Hero Section */}
      <section id="features" className="relative pt-32 pb-20 lg:pt-40 lg:pb-28 overflow-hidden">
        <DataFlowBackground />
        
        <div className="relative z-10 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid lg:grid-cols-2 gap-12 lg:gap-8 items-center">
            
            <div>
              <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-indigo-200/50 bg-indigo-50/50 text-indigo-600 text-[10px] font-extrabold uppercase tracking-widest mb-6 backdrop-blur-sm">
                <span className="w-1.5 h-1.5 rounded-full bg-indigo-500 animate-pulse"></span>
                New update &nbsp;|&nbsp; Better server events for paid ads
              </div>
              
              <h1 className="text-4xl sm:text-5xl lg:text-6xl font-extrabold tracking-tight text-slate-900 leading-[1.06] mb-6 font-display">
                Optimize Your <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-600 to-violet-600">Ad Tracking</span> with Real-Time Data
              </h1>
              
              <p className="text-[15px] text-slate-600 mb-8 leading-[1.85] max-w-md">
                Monitor server-side event quality in real time, analyze campaign attribution, and send cleaner WooCommerce signals to Meta, TikTok and GA4.
              </p>
              
              <div className="flex flex-wrap items-center gap-3 mb-10">
                <a href={CLIENT_PORTAL_URL} className="inline-flex items-center justify-center gap-2 px-6 py-2.5 text-[13px] font-bold text-white bg-gradient-to-r from-indigo-500 to-violet-600 rounded-full shadow-[0_4px_16px_rgba(79,70,229,0.25)] hover:-translate-y-0.5 hover:shadow-[0_8px_24px_rgba(79,70,229,0.4)] transition-all">
                  Get Started &rarr;
                </a>
                <a href="#product" className="inline-flex items-center justify-center gap-2 px-6 py-2.5 text-[13px] font-bold text-slate-700 bg-white border border-slate-200/80 rounded-full hover:bg-slate-50 hover:border-indigo-200 hover:-translate-y-0.5 transition-all shadow-sm">
                  How it Works
                </a>
              </div>
            </div>

            <DashboardPreview />
            
          </div>
        </div>
      </section>

      {/* Intro */}
      <div className="text-center px-6 py-16">
        <p className="font-display text-xl sm:text-2xl md:text-3xl font-semibold tracking-tight text-slate-800 max-w-3xl mx-auto leading-relaxed">
          Buykori AdSync is an ads tracking dashboard platform designed to effectively optimize and monitor your advertising campaigns.
        </p>
      </div>

      {/* Features Section */}
      <section id="product" className="py-20 relative">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-12">
            <div>
              <span className="text-indigo-600 font-extrabold tracking-widest text-[10px] uppercase mb-3 block">Key features</span>
              <h2 className="text-3xl md:text-4xl font-bold text-slate-900 tracking-tight font-display max-w-2xl">
                Powerful Ads Management Features
              </h2>
            </div>
            <div className="flex gap-1 p-1 bg-white/50 border border-slate-200/50 rounded-full backdrop-blur-sm self-start md:self-end">
              <span className="px-3.5 py-2 rounded-full text-[11px] font-bold text-slate-900 bg-white border border-slate-200 shadow-sm">Tracking</span>
              <span className="px-3.5 py-2 rounded-full text-[11px] font-bold text-slate-500">Dashboard</span>
              <span className="px-3.5 py-2 rounded-full text-[11px] font-bold text-slate-500">Ad Spend</span>
            </div>
          </div>

          <div className="grid md:grid-cols-3 gap-5">
            {features.map((feature) => (
              <div key={feature.title} className="group p-7 rounded-[18px] border border-slate-200/70 bg-white/60 backdrop-blur-xl shadow-[0_12px_40px_rgba(31,38,135,0.04)] hover:-translate-y-1 hover:border-indigo-500/30 transition-all duration-300">
                <div className="w-10 h-10 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 mb-5 group-hover:scale-110 transition-transform">
                  <feature.icon size={18} />
                </div>
                <h3 className="text-base font-bold text-slate-900 mb-2.5 font-display">{feature.title}</h3>
                <p className="text-slate-500 text-[13px] leading-[1.75] mb-6">{feature.desc}</p>
                
                <div className="flex items-center gap-2.5 mt-auto pt-5 border-t border-slate-100/80">
                  <strong className="text-2xl font-extrabold text-slate-900 tracking-tight">{feature.stat}</strong>
                  <div className="flex items-end gap-1 h-9 ml-auto">
                    {[30, 54, 42, 80].map((h, i) => (
                      <span key={i} className="w-1.5 rounded-full bg-gradient-to-b from-indigo-400 to-indigo-600 opacity-80" style={{ height: `${h}%` }}></span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Budget / Ad Spend Section */}
      <section id="solution" className="py-24 relative overflow-hidden">
        {/* Subtle decorative background */}
        <div className="absolute inset-0 bg-gradient-to-br from-indigo-50/30 to-violet-50/20 -z-10"></div>
        <div className="absolute top-1/2 left-0 -translate-y-1/2 w-[500px] h-[500px] bg-indigo-500/5 rounded-full blur-3xl -z-10 pointer-events-none"></div>

        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid lg:grid-cols-2 gap-12 items-start">
            
            <div className="pr-0 lg:pr-10">
              <span className="text-indigo-600 font-extrabold tracking-widest text-[10px] uppercase mb-3 block">Budgeting for ads</span>
              <h2 className="text-3xl md:text-4xl font-bold text-slate-900 tracking-tight mb-10 font-display leading-[1.1]">
                Manage and Optimize the Advertising Budget for Maximum Results.
              </h2>
              
              <div className="space-y-4">
                {[
                  { letter: 'A', title: 'Real-Time Tracking', desc: 'Track ad event delivery as campaigns run and quickly detect missing signals.' },
                  { letter: 'B', title: 'Budget Adjustment', desc: 'Scale spend only when event quality, product IDs and conversion signals look healthy.' },
                  { letter: 'C', title: 'Cost Per Conversion', desc: 'Use clean attribution data to compare Meta, TikTok and Google campaign performance.' }
                ].map((item) => (
                  <div key={item.letter} className="flex gap-4 p-5 rounded-[18px] bg-white/60 backdrop-blur-lg border border-slate-200/60 shadow-sm hover:border-indigo-200 transition-colors">
                    <div className="flex-shrink-0 w-[34px] h-[34px] rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 font-extrabold text-[13px]">
                      {item.letter}
                    </div>
                    <div>
                      <h4 className="text-[13px] font-bold text-slate-900 mb-1">{item.title}</h4>
                      <p className="text-slate-500 text-xs leading-[1.65]">{item.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="bg-white/80 backdrop-blur-xl rounded-[22px] border border-slate-200/70 shadow-[0_20px_50px_-12px_rgba(0,0,0,0.05)] overflow-hidden lg:mt-6 transform perspective-1000 rotate-y-[-2deg] rotate-x-[1deg] hover:rotate-y-0 hover:rotate-x-0 transition-transform duration-500">
              <div className="px-6 py-4 border-b border-slate-100/80 bg-indigo-50/40 text-[13px] font-extrabold text-slate-900">
                Ad Spend Overview
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm whitespace-nowrap">
                  <thead>
                    <tr>
                      <th className="px-6 py-3.5 text-[10px] font-extrabold text-slate-400 uppercase tracking-[0.06em] border-b border-slate-100/80">Platform</th>
                      <th className="px-6 py-3.5 text-[10px] font-extrabold text-slate-400 uppercase tracking-[0.06em] border-b border-slate-100/80">Campaign</th>
                      <th className="px-6 py-3.5 text-[10px] font-extrabold text-slate-400 uppercase tracking-[0.06em] border-b border-slate-100/80">Clicks</th>
                      <th className="px-6 py-3.5 text-[10px] font-extrabold text-slate-400 uppercase tracking-[0.06em] border-b border-slate-100/80">Impressions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100/60">
                    {[
                      ['Meta', 't-shirt_launch_may', '7,148', '92.4K'],
                      ['TikTok', 'summer_offer_cod', '4,502', '61.8K'],
                      ['GA4', 'brand_search_bd', '2,187', '28.9K'],
                      ['Direct', 'retargeting_flow', '1,044', '13.2K'],
                    ].map((row, i) => (
                      <tr key={i} className="hover:bg-indigo-50/20 transition-colors">
                        <td className="px-6 py-4 font-bold text-slate-800 text-[13px]">{row[0]}</td>
                        <td className="px-6 py-4 text-slate-600 text-[13px]">{row[1]}</td>
                        <td className="px-6 py-4 text-slate-600 text-[13px]">{row[2]}</td>
                        <td className="px-6 py-4 text-slate-600 text-[13px]">{row[3]}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

          </div>
        </div>
      </section>

      {/* Integrations Logo Cloud */}
      <section className="py-16 text-center max-w-4xl mx-auto px-4">
        <span className="text-indigo-600 font-extrabold tracking-widest text-[10px] uppercase mb-3 block">Integrations</span>
        <h2 className="text-3xl font-bold text-slate-900 tracking-tight font-display mb-3">
          Easy Integration with Your Advertising Platform
        </h2>
        <p className="text-slate-500 text-sm mb-10 max-w-xl mx-auto">
          Connect AdSync with your advertising platforms and tools from one connected workflow.
        </p>
        <div className="flex flex-wrap justify-center gap-3">
          {['Meta CAPI', 'TikTok', 'GA4', 'WooCommerce', 'Google Ads', 'LinkedIn', 'Pinterest'].map((logo) => (
            <span key={logo} className="px-5 py-2.5 bg-white/70 backdrop-blur-md border border-slate-200/80 rounded-full text-xs font-bold text-slate-500 hover:text-indigo-600 hover:border-indigo-300 hover:shadow-md hover:shadow-indigo-500/10 transition-all cursor-pointer">
              {logo}
            </span>
          ))}
        </div>
      </section>

      {/* Beyond Tracking Grid */}
      <section className="py-24 bg-gradient-to-b from-transparent to-slate-50/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col items-center text-center mb-16">
            <span className="text-indigo-600 font-extrabold tracking-widest text-[10px] uppercase mb-3">Beyond Just Tracking</span>
            <h2 className="text-3xl md:text-4xl font-bold text-slate-900 tracking-tight font-display">
              The Full Automation Stack
            </h2>
          </div>
          
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
            {[
              { title: 'Courier Auto-Sync', desc: 'Sync orders to Pathao & SteadFast instantly.', icon: Truck, color: 'text-blue-500 bg-blue-50 border-blue-100' },
              { title: 'Fake COD Protection', desc: 'Delay pixel events until delivery is confirmed.', icon: ShieldAlert, color: 'text-rose-500 bg-rose-50 border-rose-100' },
              { title: 'Custom WP Plugin', desc: 'Auto-generated plugin for 1-click installation.', icon: Puzzle, color: 'text-amber-500 bg-amber-50 border-amber-100' },
              { title: 'Multi-Tenant Portals', desc: 'Manage keys, quotas & ad performance centrally.', icon: LayoutDashboard, color: 'text-emerald-500 bg-emerald-50 border-emerald-100' },
            ].map((feature, i) => (
              <div key={i} className="group p-6 rounded-[24px] bg-white border border-slate-200/60 shadow-[0_8px_30px_rgba(0,0,0,0.04)] hover:shadow-xl hover:border-indigo-300 hover:-translate-y-1 transition-all duration-300 flex flex-col items-center text-center">
                <div className={`w-14 h-14 rounded-2xl flex items-center justify-center mb-5 border ${feature.color} group-hover:scale-110 transition-transform`}>
                  <feature.icon size={24} strokeWidth={2.5} />
                </div>
                <h3 className="text-[15px] font-bold text-slate-900 mb-2 font-display">{feature.title}</h3>
                <p className="text-[13px] text-slate-500 leading-relaxed">{feature.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Free Tools Section */}
      <section className="py-20 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="text-center max-w-2xl mx-auto mb-14">
          <span className="text-indigo-600 font-extrabold tracking-widest text-[10px] uppercase mb-3 block">Free tools</span>
          <h2 className="text-3xl md:text-4xl font-bold text-slate-900 tracking-tight font-display mb-4">
            Helpful tools for better campaign setup.
          </h2>
          <p className="text-slate-500 text-[14px] leading-relaxed">
            Useful product areas that help visitors understand and improve tracking before they install the plugin.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {freeTools.map((tool) => (
            <div key={tool.title} className="group p-7 rounded-[18px] bg-white/60 backdrop-blur-xl border border-slate-200/70 shadow-[0_12px_40px_rgba(31,38,135,0.04)] hover:-translate-y-1 hover:border-indigo-300 transition-all duration-300 min-h-[160px] flex flex-col">
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center mb-4 border ${tool.color} group-hover:scale-110 transition-transform`}>
                <tool.icon size={18} />
              </div>
              <h3 className="text-base font-bold text-slate-900 mb-2 font-display group-hover:text-indigo-600 transition-colors">{tool.title}</h3>
              <p className="text-slate-500 text-[13px] leading-[1.65] mt-auto">{tool.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Pricing Section */}
      <section id="pricing" className="py-24 text-center max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <span className="text-indigo-600 font-extrabold tracking-widest text-[10px] uppercase mb-3 block">Pricing</span>
        <h2 className="text-3xl md:text-4xl font-bold text-slate-900 tracking-tight font-display mb-14">
          Price is Just a Number, Focus on the Benefits
        </h2>

        <div className="grid md:grid-cols-3 gap-6 items-center">
          {plans.map((plan, i) => {
            const isFeatured = i === 1;
            return (
              <div key={plan.name} className={`relative p-8 rounded-[24px] text-left transition-all ${isFeatured ? 'bg-white border-2 border-indigo-500 shadow-[0_24px_60px_-15px_rgba(79,70,229,0.3)] z-10 scale-105' : 'bg-white/60 border border-slate-200/80 backdrop-blur-xl'}`}>
                <h3 className="font-display text-[15px] font-bold text-slate-900">{plan.name}</h3>
                <div className="font-display text-[44px] font-bold tracking-tight text-slate-900 mt-4 mb-1">
                  {plan.price}
                  {plan.price !== 'Custom' && <span className="text-[15px] font-semibold text-slate-400 tracking-normal">/month</span>}
                </div>
                <div className="text-xs text-slate-500 min-h-[36px] leading-[1.6]">{plan.note}</div>
                
                <button className={`w-full mt-6 py-3 rounded-full text-[13px] font-bold transition-all ${
                  isFeatured 
                    ? 'bg-gradient-to-r from-indigo-500 to-violet-600 text-white shadow-lg shadow-indigo-500/25 hover:shadow-indigo-500/40 hover:-translate-y-0.5' 
                    : 'bg-slate-50 border border-slate-200 text-slate-800 hover:bg-slate-100 hover:border-indigo-200'
                }`}>
                  {plan.name === 'Enterprise Plan' ? 'Talk to sales' : (isFeatured ? 'Start 14 Days Trial' : 'Start for free')}
                </button>

                <ul className="mt-6 space-y-3">
                  {plan.points.map((point) => (
                    <li key={point} className="flex items-start gap-2.5 text-xs text-slate-500">
                      <span className="flex-shrink-0 flex items-center justify-center w-4 h-4 rounded-full bg-indigo-50 text-indigo-600 mt-0.5">
                        <Check size={10} strokeWidth={4} />
                      </span>
                      {point}
                    </li>
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      </section>

      {/* Comparison Table */}
      <section className="py-24 max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        <span className="text-indigo-600 font-extrabold tracking-widest text-[10px] uppercase mb-3 block">Why choose us</span>
        <h2 className="text-3xl md:text-4xl font-bold text-slate-900 tracking-tight font-display mb-4">
          Buykori AdSync vs manual setup.
        </h2>
        <p className="text-slate-500 text-[14px] leading-relaxed max-w-2xl mx-auto mb-12">
          Manual server-side tracking works, but it takes more time to maintain. Buykori packages the common workflow in one product.
        </p>

        <div className="bg-white/80 backdrop-blur-xl rounded-[24px] border border-slate-200/70 shadow-xl overflow-hidden text-left">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse min-w-[600px]">
              <thead>
                <tr>
                  <th className="px-6 py-5 bg-indigo-50/40 text-[13px] font-extrabold text-slate-900 border-b border-slate-200 w-[20%]">Area</th>
                  <th className="px-6 py-5 bg-indigo-50/40 text-[13px] font-extrabold text-indigo-700 border-b border-slate-200 w-[40%]">Buykori AdSync</th>
                  <th className="px-6 py-5 bg-indigo-50/40 text-[13px] font-extrabold text-slate-900 border-b border-slate-200 w-[40%]">Manual setup</th>
                </tr>
              </thead>
              <tbody>
                {comparison.map((row, i) => (
                  <tr key={i} className="hover:bg-slate-50/50 transition-colors">
                    <td className="px-6 py-4 font-bold text-slate-900 text-[13px] border-b border-slate-100">{row.area}</td>
                    <td className="px-6 py-4 text-slate-700 text-[13px] border-b border-slate-100 leading-[1.6] bg-indigo-50/10 font-medium">
                      <div className="flex gap-2">
                        <Check size={16} className="text-emerald-500 flex-shrink-0 mt-0.5" />
                        {row.buykori}
                      </div>
                    </td>
                    <td className="px-6 py-4 text-slate-500 text-[13px] border-b border-slate-100 leading-[1.6]">
                      <div className="flex gap-2">
                        <XCircle size={16} className="text-rose-400 flex-shrink-0 mt-0.5" />
                        {row.manual}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* Testimonials */}
      <section className="py-20 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        <span className="text-indigo-600 font-extrabold tracking-widest text-[10px] uppercase mb-3 block">Customer stories</span>
        <h2 className="text-3xl md:text-4xl font-bold text-slate-900 tracking-tight font-display mb-4">
          Designed for store owners and media buyers.
        </h2>
        <p className="text-slate-500 text-[14px] leading-relaxed max-w-2xl mx-auto mb-14">
          Use cleaner server-side event data to reduce confusion before scaling ad budget.
        </p>

        <div className="grid md:grid-cols-3 gap-6">
          {testimonials.map((testi, i) => (
            <div key={i} className="p-7 rounded-[18px] bg-white/60 backdrop-blur-xl border border-slate-200/70 shadow-sm text-left hover:-translate-y-1 transition-transform">
              <div className="flex gap-1 mb-4 text-amber-400">
                {[...Array(5)].map((_, idx) => <Star key={idx} size={16} className="fill-amber-400" />)}
              </div>
              <p className="text-slate-600 text-[13px] leading-[1.8] italic mb-6">"{testi.quote}"</p>
              <div>
                <strong className="block text-slate-900 text-[13px] font-bold">{testi.author}</strong>
                <span className="text-[11px] text-slate-400 font-medium">{testi.role}</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* FAQ */}
      <section id="faq" className="py-24 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="grid md:grid-cols-[1fr_1.5fr] gap-14">
          <div>
            <span className="text-indigo-600 font-extrabold tracking-widest text-[10px] uppercase mb-3 block">FAQ</span>
            <h2 className="text-3xl md:text-4xl font-bold text-slate-900 tracking-tight font-display mb-4">
              Got questions about Buykori? We've got answers.
            </h2>
            <p className="text-slate-500 text-[14px] leading-relaxed">
              Simple answers for campaign tracking, one-page landing pages and event quality.
            </p>
          </div>
          
          <div className="flex flex-col gap-3">
            {faqs.map(([q, a], i) => (
              <div 
                key={i} 
                className={`rounded-[14px] border transition-colors ${openFaq === i ? 'bg-white border-indigo-200 shadow-md shadow-indigo-100/50' : 'bg-white/60 border-slate-200/70 hover:border-indigo-300'}`}
              >
                <button 
                  className="w-full flex items-center justify-between p-5 text-left font-bold text-sm text-slate-900"
                  onClick={() => setOpenFaq(openFaq === i ? null : i)}
                >
                  {q}
                  <ChevronDown size={18} className={`text-indigo-600 transition-transform ${openFaq === i ? 'rotate-180' : ''}`} />
                </button>
                {openFaq === i && (
                  <div className="px-5 pb-5 text-[13px] text-slate-500 leading-[1.75]">
                    {a}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="pb-24 pt-10 max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        <div className="p-10 md:p-16 rounded-[24px] bg-gradient-to-br from-indigo-50 to-violet-50/50 border border-indigo-200/60 shadow-xl backdrop-blur-xl relative overflow-hidden">
          <div className="absolute top-0 right-0 w-64 h-64 bg-indigo-500/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/3"></div>
          
          <h2 className="text-3xl md:text-4xl font-bold text-slate-900 tracking-tight font-display mb-5 relative z-10">
            Ready to Optimize Your Ads and Maximize Your Results?
          </h2>
          <p className="text-slate-600 text-[14px] leading-relaxed max-w-xl mx-auto mb-8 relative z-10">
            Start using Buykori AdSync today and take control of your ad campaigns with real-time insights.
          </p>
          <a href={CLIENT_PORTAL_URL} className="inline-flex items-center justify-center px-8 py-3.5 text-[14px] font-bold text-white bg-gradient-to-r from-indigo-500 to-violet-600 rounded-full shadow-[0_8px_24px_rgba(79,70,229,0.35)] hover:-translate-y-1 hover:shadow-[0_12px_28px_rgba(79,70,229,0.45)] transition-all relative z-10">
            Get Started for Free &rarr;
          </a>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-200/70 bg-white py-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col md:flex-row items-center justify-between gap-5">
          <Logo />
          <div className="flex gap-5 text-[12px] font-bold text-slate-500">
            <a href="#" className="hover:text-indigo-600 transition-colors">Meta</a>
            <a href="#" className="hover:text-indigo-600 transition-colors">TikTok</a>
            <a href="#" className="hover:text-indigo-600 transition-colors">GA4</a>
            <a href="#" className="hover:text-indigo-600 transition-colors">Privacy Policy</a>
          </div>
          <span className="text-[11px] text-slate-400">&copy; 2026 Buykori AdSync</span>
        </div>
      </footer>
    </div>
  );
}
