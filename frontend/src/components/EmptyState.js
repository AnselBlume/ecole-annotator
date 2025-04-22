import React from "react";
import { Header } from "./ui/header";

const EmptyState = ({ stats, userStats }) => {
  return (
    <div className="min-h-screen bg-gray-50">
      <Header stats={stats} userStats={userStats} />
      <div className="max-w-7xl mx-auto py-16 px-4 sm:py-24 sm:px-6 lg:px-8 flex flex-col items-center">
        <svg
          className="h-24 w-24 text-gray-400 mb-6"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
          xmlns="http://www.w3.org/2000/svg"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <h2 className="text-2xl font-bold text-gray-900 text-center">All Done!</h2>
        <p className="mt-2 text-sm text-gray-500 text-center">Congratulations! You've annotated all available images.</p>
      </div>
    </div>
  );
};

export default EmptyState;