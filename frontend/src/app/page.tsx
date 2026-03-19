'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function Home() {
  const router = useRouter();

  useEffect(() => {
    let isActive = true;

    const MIN_ANIMATION_MS = 2200;
    const MAX_WAIT_MS = 7000;
    const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

    const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

    const warmNewsData = async () => {
      await Promise.allSettled([
        fetch(`${API_URL}/api/news/all?count_per_company=12`, { cache: 'no-store' }),
        fetch(`${API_URL}/api/news/industry?count=20`, { cache: 'no-store' }),
        fetch(`${API_URL}/api/news/comparative`, { cache: 'no-store' }),
      ]);
    };

    const run = async () => {
      const minAnimation = sleep(MIN_ANIMATION_MS);
      const preloadWork = Promise.allSettled([
        warmNewsData(),
        router.prefetch('/news'),
      ]);

      // Wait for both animation floor and preload work, but never exceed max wait.
      await Promise.race([
        Promise.allSettled([minAnimation, preloadWork]),
        sleep(MAX_WAIT_MS),
      ]);

      if (isActive) router.replace('/news');
    };

    run();
    return () => {
      isActive = false;
    };
  }, [router]);

  return (
    <div className="intro-wrap flex h-full items-center justify-center">
      <div className="intro-glow" />

      <div className="text-center">
        <div className="scene mb-10">
          <div className="orbital orbital-a" />
          <div className="orbital orbital-b" />

          <div className="chip-stack">
            <div className="chip-layer chip-back" />
            <div className="chip-layer chip-mid" />
            <div className="chip-layer chip-front">
              <div className="chip-grid" />
              <div className="chip-core">
                <span>FLEX</span>
              </div>
            </div>
          </div>

          <div className="scanner" />
          <div className="spark spark-a" />
          <div className="spark spark-b" />
          <div className="spark spark-c" />
        </div>

        <h1 className="mb-2 text-5xl font-black tracking-tight text-white">FLEX Pulse</h1>
        <p className="mb-8 text-lg text-slate-300">Initializing News Desk</p>

        <div className="mx-auto w-64 overflow-hidden rounded-full border border-slate-600/60 bg-slate-800/70">
          <div className="h-1.5 loading-bar" />
        </div>
      </div>

      <style jsx>{`
        .intro-wrap {
          position: relative;
          overflow: hidden;
          background:
            radial-gradient(1000px 520px at 70% -10%, rgba(30, 64, 175, 0.35), transparent 60%),
            radial-gradient(900px 480px at 10% 110%, rgba(8, 145, 178, 0.24), transparent 65%),
            linear-gradient(180deg, #0a1324 0%, #08101d 52%, #050a14 100%);
        }

        .intro-glow {
          position: absolute;
          inset: 0;
          background-image:
            linear-gradient(rgba(148, 163, 184, 0.08) 1px, transparent 1px),
            linear-gradient(90deg, rgba(148, 163, 184, 0.08) 1px, transparent 1px);
          background-size: 52px 52px;
          mask-image: radial-gradient(circle at center, black 40%, transparent 85%);
          opacity: 0.35;
          animation: gridDrift 10s linear infinite;
        }

        .scene {
          position: relative;
          width: 300px;
          height: 220px;
          margin-inline: auto;
          perspective: 900px;
        }

        .chip-stack {
          position: absolute;
          inset: 30px 42px;
          transform-style: preserve-3d;
          animation: floatChip 2.8s ease-in-out infinite;
        }

        .chip-layer {
          position: absolute;
          inset: 0;
          border-radius: 26px;
          border: 1px solid rgba(148, 163, 184, 0.35);
          background: linear-gradient(135deg, rgba(14, 165, 233, 0.2), rgba(15, 23, 42, 0.7));
        }

        .chip-back {
          transform: translateZ(-36px) rotateX(14deg) rotateY(-24deg);
          opacity: 0.45;
        }

        .chip-mid {
          transform: translateZ(-18px) rotateX(12deg) rotateY(-18deg);
          opacity: 0.75;
        }

        .chip-front {
          transform: translateZ(0) rotateX(10deg) rotateY(-12deg);
          overflow: hidden;
          box-shadow:
            0 30px 60px rgba(2, 132, 199, 0.28),
            0 0 0 1px rgba(125, 211, 252, 0.35) inset;
        }

        .chip-grid {
          position: absolute;
          inset: 0;
          background-image:
            linear-gradient(rgba(125, 211, 252, 0.14) 1px, transparent 1px),
            linear-gradient(90deg, rgba(125, 211, 252, 0.14) 1px, transparent 1px);
          background-size: 16px 16px;
          opacity: 0.6;
        }

        .chip-core {
          position: absolute;
          inset: 34px;
          border-radius: 18px;
          border: 1px solid rgba(186, 230, 253, 0.5);
          background: linear-gradient(160deg, rgba(37, 99, 235, 0.65), rgba(15, 23, 42, 0.85));
          display: flex;
          align-items: center;
          justify-content: center;
          box-shadow: 0 0 40px rgba(14, 165, 233, 0.35);
        }

        .chip-core span {
          font-weight: 900;
          letter-spacing: 0.12em;
          font-size: 22px;
          color: #e2e8f0;
          text-shadow: 0 0 18px rgba(125, 211, 252, 0.45);
        }

        .orbital {
          position: absolute;
          border-radius: 9999px;
          border: 1px dashed rgba(125, 211, 252, 0.28);
          transform-style: preserve-3d;
        }

        .orbital-a {
          inset: 8px;
          animation: spinA 6s linear infinite;
        }

        .orbital-b {
          inset: 24px;
          animation: spinB 5s linear infinite reverse;
        }

        .scanner {
          position: absolute;
          left: 26px;
          right: 26px;
          top: 50%;
          height: 2px;
          background: linear-gradient(90deg, transparent, #22d3ee, transparent);
          filter: drop-shadow(0 0 10px rgba(34, 211, 238, 0.75));
          animation: scan 1.6s ease-in-out infinite;
        }

        .spark {
          position: absolute;
          width: 8px;
          height: 8px;
          border-radius: 9999px;
          background: #67e8f9;
          box-shadow: 0 0 16px rgba(103, 232, 249, 0.85);
        }

        .spark-a {
          top: 18px;
          left: 24px;
          animation: sparkMoveA 2.1s ease-in-out infinite;
        }

        .spark-b {
          right: 36px;
          top: 42px;
          animation: sparkMoveB 1.8s ease-in-out infinite;
        }

        .spark-c {
          bottom: 16px;
          left: 52%;
          animation: sparkMoveC 2.3s ease-in-out infinite;
        }

        .loading-bar {
          width: 36%;
          background: linear-gradient(90deg, #0ea5e9, #22d3ee 45%, #38bdf8);
          animation: loadBar 2.4s ease-in-out forwards;
        }

        @keyframes floatChip {
          0%, 100% { transform: translateY(0px) rotateX(-1deg); }
          50% { transform: translateY(-12px) rotateX(1.8deg); }
        }

        @keyframes spinA {
          from { transform: rotateX(70deg) rotateZ(0deg); }
          to { transform: rotateX(70deg) rotateZ(360deg); }
        }

        @keyframes spinB {
          from { transform: rotateY(70deg) rotateZ(0deg); }
          to { transform: rotateY(70deg) rotateZ(360deg); }
        }

        @keyframes scan {
          0%, 100% { transform: translateY(-52px); opacity: 0.2; }
          50% { transform: translateY(52px); opacity: 1; }
        }

        @keyframes sparkMoveA {
          0%, 100% { transform: translate(0, 0); opacity: 0.35; }
          50% { transform: translate(30px, 18px); opacity: 1; }
        }

        @keyframes sparkMoveB {
          0%, 100% { transform: translate(0, 0); opacity: 0.45; }
          50% { transform: translate(-22px, 26px); opacity: 1; }
        }

        @keyframes sparkMoveC {
          0%, 100% { transform: translate(0, 0); opacity: 0.5; }
          50% { transform: translate(-36px, -20px); opacity: 1; }
        }

        @keyframes loadBar {
          0% { width: 16%; }
          100% { width: 100%; }
        }

        @keyframes gridDrift {
          from { transform: translate3d(0, 0, 0); }
          to { transform: translate3d(24px, 14px, 0); }
        }
      `}</style>
    </div>
  );
}
