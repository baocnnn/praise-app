import { useState, useEffect } from 'react';
import { apiService } from '../services/api';

function MyProfile() {
  const [user, setUser] = useState(null);
  const [myPraise, setMyPraise] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [userResponse, praiseResponse] = await Promise.all([
          apiService.getCurrentUser(),
          apiService.getMyPraise(),
        ]);

        setUser(userResponse.data);
        setMyPraise(praiseResponse.data);
      } catch (error) {
        console.error('Error fetching profile:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, []);

  if (loading) {
    return (
      <div style={styles.container}>
        <h1>Loading...</h1>
      </div>
    );
  }
  if (!user) {
    return (
        <div style={styles.container}>
            <h1>Error loading profile</h1>
        </div>
    );
  }

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        <h1 style={styles.name}>
          {user.first_name} {user.last_name}
        </h1>
        <div style={styles.pointsBadge}>
          {user.points_balance} Points
        </div>
      </div>

      <div style={styles.section}>
        <h2 style={styles.sectionTitle}>Praise I've Received ({myPraise.length})</h2>
        
        {myPraise.length === 0 ? (
          <p style={styles.emptyMessage}>No praise yet. Keep up the great work!</p>
        ) : (
          <div style={styles.praiseList}>
            {myPraise.map((praise) => (
              <div key={praise.id} style={styles.praiseCard}>
                <div style={styles.praiseHeader}>
                  <span style={styles.coreValue}>{praise.core_value.name}</span>
                  <span style={styles.points}>+{praise.points_awarded} pts</span>
                </div>
                <p style={styles.message}>"{praise.message}"</p>
                <div style={styles.footer}>
                  <span style={styles.from}>
                    From: {praise.giver.first_name} {praise.giver.last_name}
                  </span>
                  <span style={styles.date}>
                    {new Date(praise.created_at).toLocaleDateString()}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

const styles = {
  container: {
    maxWidth: '900px',
    margin: '0 auto',
    padding: '40px 20px',
  },
  header: {
    backgroundColor: 'white',
    borderRadius: '8px',
    padding: '30px',
    boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
    marginBottom: '30px',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  name: {
    margin: 0,
    color: '#333',
  },
  pointsBadge: {
    backgroundColor: '#28a745',
    color: 'white',
    padding: '12px 24px',
    borderRadius: '25px',
    fontSize: '18px',
    fontWeight: 'bold',
  },
  section: {
    backgroundColor: 'white',
    borderRadius: '8px',
    padding: '30px',
    boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
  },
  sectionTitle: {
    marginBottom: '20px',
    color: '#333',
  },
  emptyMessage: {
    color: '#666',
    textAlign: 'center',
    padding: '40px',
  },
  praiseList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '15px',
  },
  praiseCard: {
    border: '1px solid #e0e0e0',
    borderRadius: '6px',
    padding: '20px',
    backgroundColor: '#f9f9f9',
  },
  praiseHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    marginBottom: '10px',
  },
  coreValue: {
    color: '#007bff',
    fontSize: '12px',
    fontWeight: 'bold',
    textTransform: 'uppercase',
  },
  points: {
    color: '#28a745',
    fontSize: '14px',
    fontWeight: 'bold',
  },
  message: {
    fontSize: '16px',
    color: '#333',
    margin: '10px 0',
    fontStyle: 'italic',
  },
  footer: {
    display: 'flex',
    justifyContent: 'space-between',
    marginTop: '10px',
    fontSize: '14px',
    color: '#666',
  },
  from: {},
  date: {},
};

export default MyProfile;