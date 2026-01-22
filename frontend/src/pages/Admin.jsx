import { useState, useEffect } from 'react';
import { apiService } from '../services/api';

function Admin() {
  const [activeTab, setActiveTab] = useState('core-values');
  
  // Core Values
  const [coreValues, setCoreValues] = useState([]);
  const [newCoreValue, setNewCoreValue] = useState({ name: '', description: '' });
  
  // Rewards
  const [rewards, setRewards] = useState([]);
  const [newReward, setNewReward] = useState({ name: '', description: '', point_cost: '' });
  
  // Redemptions
  const [redemptions, setRedemptions] = useState([]);
  
  // Users
  const [users, setUsers] = useState([]);
  
  const [message, setMessage] = useState({ type: '', text: '' });

  useEffect(() => {
    fetchData();
  }, [activeTab]);

  const fetchData = async () => {
    try {
      if (activeTab === 'core-values') {
        const response = await apiService.getCoreValues();
        setCoreValues(response.data);
      } else if (activeTab === 'rewards') {
        const response = await apiService.getRewards();
        setRewards(response.data);
      } else if (activeTab === 'redemptions') {
        const response = await apiService.getAllRedemptions();
        setRedemptions(response.data);
      } else if (activeTab === 'users') {
        const response = await apiService.getAllUsers();
        setUsers(response.data);
      }
    } catch (error) {
      console.error('Error fetching data:', error);
    }
  };

  const handleCreateCoreValue = async (e) => {
    e.preventDefault();
    try {
      await apiService.createCoreValue(newCoreValue.name, newCoreValue.description);
      setMessage({ type: 'success', text: 'Core value created!' });
      setNewCoreValue({ name: '', description: '' });
      fetchData();
      setTimeout(() => setMessage({ type: '', text: '' }), 3000);
    } catch (error) {
      setMessage({ type: 'error', text: 'Failed to create core value' });
    }
  };

  const handleDeleteCoreValue = async (id) => {
    if (!window.confirm('Are you sure you want to delete this core value?')) return;
    try {
      await apiService.deleteCoreValue(id);
      setMessage({ type: 'success', text: 'Core value deleted!' });
      fetchData();
      setTimeout(() => setMessage({ type: '', text: '' }), 3000);
    } catch (error) {
      setMessage({ type: 'error', text: 'Failed to delete core value' });
    }
  };

  const handleCreateReward = async (e) => {
    e.preventDefault();
    try {
      await apiService.createReward({
        name: newReward.name,
        description: newReward.description,
        point_cost: parseInt(newReward.point_cost)
      });
      setMessage({ type: 'success', text: 'Reward created!' });
      setNewReward({ name: '', description: '', point_cost: '' });
      fetchData();
      setTimeout(() => setMessage({ type: '', text: '' }), 3000);
    } catch (error) {
      setMessage({ type: 'error', text: 'Failed to create reward' });
    }
  };

  const handleDeleteReward = async (id) => {
    if (!window.confirm('Are you sure you want to delete this reward?')) return;
    try {
      await apiService.deleteReward(id);
      setMessage({ type: 'success', text: 'Reward deleted!' });
      fetchData();
      setTimeout(() => setMessage({ type: '', text: '' }), 3000);
    } catch (error) {
      setMessage({ type: 'error', text: 'Failed to delete reward' });
    }
  };

  const handleFulfillRedemption = async (id) => {
    try {
      await apiService.fulfillRedemption(id);
      setMessage({ type: 'success', text: 'Redemption fulfilled!' });
      fetchData();
      setTimeout(() => setMessage({ type: '', text: '' }), 3000);
    } catch (error) {
      setMessage({ type: 'error', text: 'Failed to fulfill redemption' });
    }
  };

  return (
    <div style={styles.container}>
      <h1 style={styles.title}>Admin Panel</h1>

      {message.text && (
        <div style={message.type === 'success' ? styles.success : styles.error}>
          {message.text}
        </div>
      )}

      <div style={styles.tabs}>
        <button
          onClick={() => setActiveTab('core-values')}
          style={{...styles.tab, ...(activeTab === 'core-values' ? styles.activeTab : {})}}
        >
          Core Values
        </button>
        <button
          onClick={() => setActiveTab('rewards')}
          style={{...styles.tab, ...(activeTab === 'rewards' ? styles.activeTab : {})}}
        >
          Rewards
        </button>
        <button
          onClick={() => setActiveTab('redemptions')}
          style={{...styles.tab, ...(activeTab === 'redemptions' ? styles.activeTab : {})}}
        >
          Redemptions
        </button>
        <button
          onClick={() => setActiveTab('users')}
          style={{...styles.tab, ...(activeTab === 'users' ? styles.activeTab : {})}}
        >
          Users
        </button>
      </div>

      <div style={styles.content}>
        {/* CORE VALUES TAB */}
        {activeTab === 'core-values' && (
          <div>
            <h2>Manage Core Values</h2>
            
            <form onSubmit={handleCreateCoreValue} style={styles.form}>
              <h3>Add New Core Value</h3>
              <input
                type="text"
                placeholder="Name (e.g., Above and Beyond)"
                value={newCoreValue.name}
                onChange={(e) => setNewCoreValue({...newCoreValue, name: e.target.value})}
                required
                style={styles.input}
              />
              <textarea
                placeholder="Description"
                value={newCoreValue.description}
                onChange={(e) => setNewCoreValue({...newCoreValue, description: e.target.value})}
                rows="3"
                style={styles.textarea}
              />
              <button type="submit" style={styles.button}>Add Core Value</button>
            </form>

            <h3 style={{marginTop: '30px'}}>Existing Core Values</h3>
            <div style={styles.list}>
              {coreValues.map((cv) => (
                <div key={cv.id} style={styles.card}>
                  <div>
                    <h4 style={{margin: '0 0 5px 0'}}>{cv.name}</h4>
                    <p style={{margin: 0, color: '#666', fontSize: '14px'}}>{cv.description}</p>
                  </div>
                  <button
                    onClick={() => handleDeleteCoreValue(cv.id)}
                    style={styles.deleteButton}
                  >
                    Delete
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* REWARDS TAB */}
        {activeTab === 'rewards' && (
          <div>
            <h2>Manage Rewards</h2>
            
            <form onSubmit={handleCreateReward} style={styles.form}>
              <h3>Add New Reward</h3>
              <input
                type="text"
                placeholder="Name (e.g., Coffee Drink)"
                value={newReward.name}
                onChange={(e) => setNewReward({...newReward, name: e.target.value})}
                required
                style={styles.input}
              />
              <textarea
                placeholder="Description"
                value={newReward.description}
                onChange={(e) => setNewReward({...newReward, description: e.target.value})}
                rows="2"
                style={styles.textarea}
              />
              <input
                type="number"
                placeholder="Point Cost (e.g., 25)"
                value={newReward.point_cost}
                onChange={(e) => setNewReward({...newReward, point_cost: e.target.value})}
                required
                style={styles.input}
              />
              <button type="submit" style={styles.button}>Add Reward</button>
            </form>

            <h3 style={{marginTop: '30px'}}>Existing Rewards</h3>
            <div style={styles.list}>
              {rewards.map((reward) => (
                <div key={reward.id} style={styles.card}>
                  <div>
                    <h4 style={{margin: '0 0 5px 0'}}>{reward.name}</h4>
                    <p style={{margin: '0 0 5px 0', color: '#666', fontSize: '14px'}}>
                      {reward.description}
                    </p>
                    <p style={{margin: 0, fontWeight: 'bold', color: '#007bff'}}>
                      {reward.point_cost} points
                    </p>
                  </div>
                  <button
                    onClick={() => handleDeleteReward(reward.id)}
                    style={styles.deleteButton}
                  >
                    Delete
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* REDEMPTIONS TAB */}
        {activeTab === 'redemptions' && (
          <div>
            <h2>Manage Redemptions</h2>
            <div style={styles.list}>
              {redemptions.length === 0 ? (
                <p style={{textAlign: 'center', color: '#666'}}>No redemptions yet</p>
              ) : (
                redemptions.map((redemption) => (
                  <div key={redemption.id} style={styles.card}>
                    <div>
                      <h4 style={{margin: '0 0 5px 0'}}>{redemption.reward.name}</h4>
                      <p style={{margin: '0 0 5px 0', fontSize: '14px'}}>
                        Redeemed by: User #{redemption.user_id}
                      </p>
                      <p style={{margin: '0 0 5px 0', fontSize: '14px'}}>
                        Points: {redemption.points_spent}
                      </p>
                      <p style={{margin: 0, fontSize: '14px'}}>
                        Date: {new Date(redemption.redeemed_at).toLocaleDateString()}
                      </p>
                    </div>
                    <div>
                      <span style={{
                        ...styles.statusBadge,
                        backgroundColor: redemption.status === 'fulfilled' ? '#28a745' : '#ffc107'
                      }}>
                        {redemption.status}
                      </span>
                      {redemption.status === 'pending' && (
                        <button
                          onClick={() => handleFulfillRedemption(redemption.id)}
                          style={{...styles.button, marginTop: '10px'}}
                        >
                          Mark Fulfilled
                        </button>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        )}

        {/* USERS TAB */}
        {activeTab === 'users' && (
          <div>
            <h2>All Users</h2>
            <div style={styles.list}>
              {users.map((user) => (
                <div key={user.id} style={styles.card}>
                  <div>
                    <h4 style={{margin: '0 0 5px 0'}}>
                      {user.first_name} {user.last_name}
                    </h4>
                    <p style={{margin: '0 0 5px 0', fontSize: '14px', color: '#666'}}>
                      {user.email}
                    </p>
                  </div>
                  <div style={{
                    ...styles.statusBadge,
                    backgroundColor: '#007bff'
                  }}>
                    {user.points_balance} points
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

const styles = {
  container: {
    maxWidth: '1000px',
    margin: '0 auto',
    padding: '40px 20px',
  },
  title: {
    marginBottom: '30px',
    color: '#333',
  },
  tabs: {
    display: 'flex',
    gap: '10px',
    marginBottom: '30px',
    borderBottom: '2px solid #e0e0e0',
  },
  tab: {
    padding: '10px 20px',
    backgroundColor: 'transparent',
    border: 'none',
    cursor: 'pointer',
    fontSize: '16px',
    color: '#666',
    borderBottom: '3px solid transparent',
  },
  activeTab: {
    color: '#007bff',
    borderBottom: '3px solid #007bff',
    fontWeight: 'bold',
  },
  content: {
    backgroundColor: 'white',
    borderRadius: '8px',
    padding: '30px',
    boxShadow: '0 2px 10px rgba(0,0,0,0.1)',
  },
  form: {
    border: '1px solid #e0e0e0',
    borderRadius: '8px',
    padding: '20px',
    marginBottom: '20px',
  },
  input: {
    width: '100%',
    padding: '12px',
    fontSize: '16px',
    border: '1px solid #ddd',
    borderRadius: '4px',
    marginBottom: '15px',
  },
  textarea: {
    width: '100%',
    padding: '12px',
    fontSize: '16px',
    border: '1px solid #ddd',
    borderRadius: '4px',
    marginBottom: '15px',
    fontFamily: 'inherit',
    resize: 'vertical',
  },
  button: {
    padding: '10px 20px',
    backgroundColor: '#28a745',
    color: 'white',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
    fontSize: '14px',
  },
  list: {
    display: 'flex',
    flexDirection: 'column',
    gap: '15px',
  },
  card: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    border: '1px solid #e0e0e0',
    borderRadius: '6px',
    padding: '15px',
  },
  deleteButton: {
    padding: '8px 16px',
    backgroundColor: '#dc3545',
    color: 'white',
    border: 'none',
    borderRadius: '4px',
    cursor: 'pointer',
    fontSize: '14px',
  },
  statusBadge: {
    padding: '6px 12px',
    borderRadius: '12px',
    fontSize: '12px',
    color: 'white',
    textTransform: 'uppercase',
    fontWeight: 'bold',
  },
  success: {
    backgroundColor: '#d4edda',
    color: '#155724',
    padding: '12px',
    borderRadius: '4px',
    marginBottom: '20px',
  },
  error: {
    backgroundColor: '#f8d7da',
    color: '#721c24',
    padding: '12px',
    borderRadius: '4px',
    marginBottom: '20px',
  },
};

export default Admin;