'use client';

import type { HTMLAttributes } from 'react';

import { cn } from '@/lib/utils';

interface SkeletonProps extends HTMLAttributes<HTMLDivElement> {}

export function Skeleton({ className, ...props }: SkeletonProps) {
  return (
    <div
      {...props}
      className={cn(
        'animate-pulse rounded-md bg-slate-200',
        className
      )}
    />
  );
}

export function CardSkeleton() {
  return (
    <div className="bg-white rounded-2xl shadow-lg border border-slate-100 p-6">
      <div className="flex items-center justify-between mb-4">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-10 w-10 rounded-xl" />
      </div>
      <Skeleton className="h-8 w-20 mb-2" />
      <Skeleton className="h-4 w-24" />
    </div>
  );
}

export function ChartSkeleton() {
  return (
    <div className="bg-white rounded-2xl shadow-lg border border-slate-100 p-6">
      <Skeleton className="h-6 w-40 mb-6" />
      <div className="flex items-end gap-2 h-48">
        {[...Array(6)].map((_, i) => (
          <Skeleton
            key={i}
            className="flex-1"
            style={{ height: `${Math.random() * 60 + 40}%` }}
          />
        ))}
      </div>
    </div>
  );
}

export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="bg-white rounded-2xl shadow-lg border border-slate-100 p-6">
      <Skeleton className="h-6 w-48 mb-6" />
      <div className="space-y-3">
        {[...Array(rows)].map((_, i) => (
          <div key={i} className="flex gap-4">
            <Skeleton className="h-10 w-10 rounded-lg" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-48" />
            </div>
            <Skeleton className="h-6 w-16 rounded-full" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function DashboardSkeleton() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-slate-100 p-6">
      {/* Header */}
      <div className="mb-8">
        <Skeleton className="h-10 w-80 mb-2" />
        <Skeleton className="h-5 w-64" />
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        {[...Array(4)].map((_, i) => (
          <CardSkeleton key={i} />
        ))}
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <ChartSkeleton />
        <ChartSkeleton />
      </div>

      {/* Table */}
      <TableSkeleton rows={5} />
    </div>
  );
}

export function CompanyCardSkeleton() {
  return (
    <div className="bg-white rounded-2xl shadow-lg border border-slate-100 p-6 hover:shadow-xl transition-shadow">
      <div className="flex items-center gap-4 mb-4">
        <Skeleton className="h-12 w-12 rounded-xl" />
        <div>
          <Skeleton className="h-6 w-32 mb-1" />
          <Skeleton className="h-4 w-20" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <Skeleton className="h-3 w-16 mb-1" />
          <Skeleton className="h-5 w-12" />
        </div>
        <div>
          <Skeleton className="h-3 w-16 mb-1" />
          <Skeleton className="h-5 w-12" />
        </div>
      </div>
    </div>
  );
}

export function ChatSkeleton() {
  return (
    <div className="flex gap-4 p-4">
      <Skeleton className="h-10 w-10 rounded-full flex-shrink-0" />
      <div className="flex-1 space-y-2">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-4 w-2/3" />
      </div>
    </div>
  );
}
