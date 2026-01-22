import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { authService } from '../services/auth';
import './Navbar.css';

function Navbar() {
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  const handleLogout = () => {
    authService.removeToken();
    navigate('/login');
  };

  return (
    <nav className="navbar">
      <div className="navbar-container">
        <h2 className="navbar-logo">Praise App</h2>
        
        <button className="hamburger" onClick={() => setMenuOpen(!menuOpen)}>
          ☰
        </button>

        <div className="desktop-links">
          <Link to="/dashboard" className="nav-link">Dashboard</Link>
          <Link to="/give-praise" className="nav-link">Give Praise</Link>
          <Link to="/my-profile" className="nav-link">My Profile</Link>
          <Link to="/rewards" className="nav-link">Rewards</Link>
          <Link to="/admin" className="nav-link">Admin</Link>
          <button onClick={handleLogout} className="logout-button">
            Logout
          </button>
        </div>

        {menuOpen && (
          <div className="mobile-menu">
            <Link to="/dashboard" className="mobile-link" onClick={() => setMenuOpen(false)}>
              Dashboard
            </Link>
            <Link to="/give-praise" className="mobile-link" onClick={() => setMenuOpen(false)}>
              Give Praise
            </Link>
            <Link to="/my-profile" className="mobile-link" onClick={() => setMenuOpen(false)}>
              My Profile
            </Link>
            <Link to="/rewards" className="mobile-link" onClick={() => setMenuOpen(false)}>
              Rewards
            </Link>
            <Link to="/admin" className="mobile-link" onClick={() => setMenuOpen(false)}>
              Admin
            </Link>
            <button onClick={handleLogout} className="logout-button" style={{width: '100%', marginTop: '10px'}}>
              Logout
            </button>
          </div>
        )}
      </div>
    </nav>
  );
}

export default Navbar;