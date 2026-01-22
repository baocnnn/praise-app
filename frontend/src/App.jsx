import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import GivePraise from './pages/GivePraise';
import MyProfile from './pages/MyProfile';
import Rewards from './pages/Rewards';
import ProtectedRoute from './components/ProtectedRoute';
import Navbar from './components/Navbar';
import Admin from './pages/Admin';
import { authService } from './services/auth';

function App() {
  const isAuthenticated = authService.isAuthenticated();

  return (
    <Router>
      {isAuthenticated && <Navbar />}
      
      <Routes>
        {/* Public route */}
        <Route path="/login" element={<Login />} />

        {/* Protected routes */}
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <Dashboard />
            </ProtectedRoute>
          }
        />
        <Route
          path="/give-praise"
          element={
            <ProtectedRoute>
              <GivePraise />
            </ProtectedRoute>
          }
        />
        <Route
          path="/my-profile"
          element={
            <ProtectedRoute>
              <MyProfile />
            </ProtectedRoute>
          }
        />
        <Route
          path="/rewards"
          element={
            <ProtectedRoute>
              <Rewards />
            </ProtectedRoute>
          }
        />
        <Route
          path="/admin"
          element={
            <ProtectedRoute>
              <Admin />
            </ProtectedRoute>
          }
        />

        {/* Default redirect */}
        <Route 
          path="/" 
          element={<Navigate to={isAuthenticated ? "/dashboard" : "/login"} replace />} 
        />
      </Routes>
    </Router>
  );
}

export default App;