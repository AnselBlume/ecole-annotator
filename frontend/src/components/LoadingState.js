import React from "react";
import { Header } from "./ui/header";

const LoadingState = ({ stats, userStats }) => {
  return (
    <div className="min-h-screen bg-gray-50">
      <Header stats={stats} userStats={userStats} />
      <div className="max-w-7xl mx-auto py-16 px-4 sm:py-24 sm:px-6 lg:px-8 flex flex-col items-center">
        <div className="w-16 h-16 border-4 border-blue-500 border-t-transparent rounded-full animate-spin mb-6"></div>
        <h2 className="text-2xl font-bold text-gray-900 text-center">Loading next image...</h2>
        <p className="mt-2 text-sm text-gray-500 text-center">Please wait while we prepare the next image for annotation.</p>
      </div>
    </div>
  );
};

export default LoadingState;