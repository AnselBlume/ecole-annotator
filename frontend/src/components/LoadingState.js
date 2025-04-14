import React from "react";
import { Header } from "./ui/header";

const LoadingState = ({ stats }) => {
  return (
    <div className="min-h-screen bg-gray-50">
      <Header stats={stats} />
      <div className="flex items-center justify-center h-[80vh]">
        <div className="text-xl font-medium text-gray-700">
          Loading...
        </div>
      </div>
    </div>
  );
};

export default LoadingState;