import React from "react";
import { Header } from "./ui/header";

const EmptyState = ({ stats }) => {
  return (
    <div className="min-h-screen bg-gray-50">
      <Header stats={stats} />
      <div className="max-w-2xl mx-auto mt-20 text-center p-10 bg-white rounded-lg shadow-sm">
        <div className="text-5xl mb-4">🎉</div>
        <h2 className="text-2xl font-bold text-gray-800 mb-2">All Done!</h2>
        <p className="text-gray-600">No more images to annotate.</p>
      </div>
    </div>
  );
};

export default EmptyState;